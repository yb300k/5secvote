#-*- coding: utf-8 -*-

from __future__ import unicode_literals

import errno
import logging
import os
import re
import redis
import time

from flask import Flask, request, abort, send_from_directory, url_for

from linebot import (
    LineBotApi, WebhookHandler,
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    TemplateSendMessage, ConfirmTemplate, MessageTemplateAction,
    ButtonsTemplate, URITemplateAction, PostbackTemplateAction,
    CarouselTemplate, CarouselColumn, PostbackEvent,
    UnfollowEvent, FollowEvent,ImageSendMessage,
    ImagemapSendMessage, MessageImagemapAction, BaseSize, ImagemapArea
)

from const import *
from utility import *
from mutex import Mutex

app = Flask(__name__)
app.config.from_object('config')
redis = redis.from_url(app.config['REDIS_URL'])
stream_handler = logging.StreamHandler()
app.logger.addHandler(stream_handler)
app.logger.setLevel(app.config['LOG_LEVEL'])
line_bot_api = LineBotApi(app.config['CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(app.config['CHANNEL_SECRET'])

@app.route('/callback', methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info('Request body: ' + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@app.route('/images/button/<size>', methods=['GET'])
def download_imageam(size):
    filename = JOIN_IMAGE_FILENAME.format(size)
    return send_from_directory(os.path.join(app.root_path, 'static', 'button'),
            filename)

@app.route('/images/tmp/<number>/<size>', methods=['GET'])
def download_vote(number, size):
    filename = 'vote-' + size + '.png'
    return send_from_directory(os.path.join(app.root_path, 'static', 'tmp', number), filename)


@app.route('/images/planning_poker/<size>', methods=['GET'])
def download_imagemap(size):
    filename = POKER_IMAGE_FILENAME.format(size)
    return send_from_directory(os.path.join(app.root_path, 'static', 'planning_poker'),
            filename)

def getUtfName(profile):
    if isinstance(profile.display_name,str):
        return profile.display_name.decode('utf-8')
    else:
        return profile.display_name

@handler.add(FollowEvent)
def handle_follow(event):
#友達追加イベント、ここでredisへの登録を行う
    sourceId = getSourceId(event.source)
    profile = line_bot_api.get_profile(sourceId)
    display_name = getUtfName(profile)
    picture_url = profile.picture_url
    redis.hset(sourceId,'name',display_name)
    redis.hset(sourceId,'pict',picture_url)

    line_bot_api.push_message(
        sourceId, TextSendMessage(text='こんにちわ\uD83D\uDE04\n'+
        'みんなでせーのでタイミングを合わせて参加ボタンを押してね\uD83D\uDE03'))

    line_bot_api.push_message(
        sourceId,generateJoinButton())

@handler.add(UnfollowEvent)
def handle_unfollow(event):
    sourceId = getSourceId(event.source)
    redis.hset(sourceId,'voted','N')
    current = redis.hget(sourceId,'current')
    if current != '-':
        remove_member(current,sourceId)
    redis.hset(sourceId,'current','-')

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    text = event.message.text
    sourceId = getSourceId(event.source)
    matcher = re.match(r'^#(\d+) (.+)', text)

    if text == 'join':#メンバ集め
        number = str(redis.get('maxVoteKey')).encode('utf-8')
        join_mutex = Mutex(redis, JOIN_MUTEX_KEY_PREFIX+ number)
        join_mutex.lock()
        redis.sadd(number,sourceId)
        redis.hset(number+'_member',redis.scard(number),sourceId)
        redis.hset(sourceId,'current',number)

        if join_mutex.is_lock():
            time.sleep(JOIN_MUTEX_TIMEOUT)

            push_all(number,TextSendMessage(text='投票No.'+str(number)+' （全参加者'+ str(redis.scard(number)) +
                '人）の投票板です\uD83D\uDE04\n'+
                '5秒間投票をスタートするなら 投票開始≫ ボタンを押してね\uD83D\uDE03'))
            push_all(number,generate_planning_poker_message(number))
            join_mutex.unlock()
            redis.incr('maxVoteKey')

    elif text == 'add':
        current = redis.hget(sourceId,'current')
        if current != '-':
            remove_member(current,sourceId)
        line_bot_api.push_message(
            sourceId, TextSendMessage(text='参加したい投票No.を入力してください\uD83D\uDE03'))
        redis.hset(sourceId,'status','number_wait')

    elif matcher is not None:
        number = matcher.group(1)
        value = matcher.group(2)
        current = redis.hget(sourceId,'current').encode('utf-8')
        if current != number:
            line_bot_api.push_message(
                sourceId, TextSendMessage(text='投票板が古かった？もう一度お願いします！'))
            line_bot_api.push_message(
                sourceId,generate_planning_poker_message(current))
            return

        if value == '11':#退出
            resign_operation(number,sourceId)
            return

        status = redis.hget('status_'+number,'status')
        if status is None:
            vote_mutex = Mutex(redis, VOTE_MUTEX_KEY_PREFIX + number)
            if value == '0':#開始
                vote_mutex.lock()
                if vote_mutex.is_lock():
                    push_all(number,TextSendMessage(text='5秒間投票をはじめます！名前をタップして投票してね\uD83D\uDE04'))
                    redis.hset('status_'+number,'status','inprogress')
                    time.sleep(2)
                    push_all(number,TextSendMessage(text='あと3秒！'))
                    time.sleep(3)
                    push_all(number,TextSendMessage(text='－\uD83D\uDD52投票終了\uD83D\uDD52－'))
                    vote_mutex.unlock()
                    redis.delete('status_'+number)
                    member_list = redis.smembers(number)
                    for memberid in member_list:
                        redis.hset(memberid,'voted','N')

                    push_result_message(number)
                    #結果発表後の結果クリア
                    redis.delete('res_' + number)
                    refresh_board(number)
                    return
            else:
                line_bot_api.push_message(
                    sourceId, TextSendMessage(text='投票開始ボタンがまだ押されていないようです\uD83D\uDCA6'))
        else:
            if redis.hget(sourceId,'voted') == 'Y':
                line_bot_api.push_message(
                    sourceId, TextSendMessage(text='すでに投票済です・・結果集計まで待ってね\uD83D\uDE04'))
                return
            elif value == '0':
                line_bot_api.push_message(
                    sourceId, TextSendMessage(text='もうはじまってるよ、誰かに投票して！\uD83D\uDE04'))
            elif value == '11':
                resign_operation(number,sourceId)
            else:
                #異常値処理省略
                redis.hincrby('res_' + number, value)
                redis.hset(sourceId,'voted','Y')
    else:
        current = redis.hget(sourceId,'current')
        if current is not None and current != '-':
            display_name = getUtfName(line_bot_api.get_profile(sourceId))
            push_all(current,TextSendMessage(text=display_name + ':' + text))
        elif redis.hget(sourceId,'status') == 'number_wait':
            if text == '0':
                redis.hdel(sourceId,'status')
                line_bot_api.push_message(
                    sourceId, TextSendMessage(text='始めるときは参加！ボタンをみんなと一緒に押してね\uD83D\uDE04'))
                line_bot_api.push_message(
                    sourceId,generateJoinButton())
            elif redis.exists(text) == 1:
                redis.hdel(sourceId,'status')
                redis.sadd(text,sourceId)
                redis.hset(text+'_member',redis.scard(text),sourceId)
                redis.hset(sourceId,'current',text)
                if redis.hget('status_'+text,'status') is None:
                    push_all(text,TextSendMessage(text='メンバーが増えたので再度投票板を表示します'))
                    push_all(text,TextSendMessage(text='投票No.'+str(text)+' （全参加者'+ str(redis.scard(text)) +
                        '人）の投票板です\uD83D\uDE04\n'+
                        '5秒間投票をスタートするなら 投票開始≫ ボタンを押してね\uD83D\uDE03'))
                    push_all(text,generate_planning_poker_message(text))
            else:
                line_bot_api.push_message(
                    sourceId, TextSendMessage(text='見つからないです・・参加したい投票No.を再入力してね\uD83D\uDE22（初期画面に戻るなら 0 ）'))

def resign_operation(number,sourceId):
    line_bot_api.push_message(
        sourceId, TextSendMessage(text='この投票から抜けます。また始めるときは参加！ボタンをみんなと一緒に押してね\uD83D\uDE04'))
    remove_member(number,sourceId)
    line_bot_api.push_message(
        sourceId,generateJoinButton())

def remove_member(number,sourceId):
    if redis.scard(number) == 1:
        redis.srem(number,sourceId)
        redis.delete(number+'_member')
    else:
        redis.srem(number,sourceId)

    redis.hset(sourceId,'current','-')
    redis.hset(sourceId,'voted','N')
    redis.hdel(sourceId,'status')

def refresh_board(number):
    redis.delete(number+'_member')
    data = redis.smembers(number)
    i = 1
    for value in data:
        redis.hset(number+'_member',i,value)
        i += 1

    push_all(number,TextSendMessage(text='もう1回やる？\uD83D\uDE03 抜ける人は 退出する ボタンを押してね\uD83D\uDE4F'))
    push_all(number,TextSendMessage(text='投票No.'+str(number)+' （全参加者'+ str(redis.scard(number)) +
        '人）の投票板です\uD83D\uDE04\n'+
        '5秒間投票をスタートするなら 投票開始≫ ボタンを押してね\uD83D\uDE03'))
    push_all(number,generate_planning_poker_message(number))

def getNameFromNum(vote_num,field_pos):
    sourceId = redis.hget(vote_num+'_member',field_pos)
    return redis.hget(sourceId,'name')

def push_result_message(vote_num):
    answer_count = redis.hlen('res_'+vote_num)
    if answer_count == 0:
        push_all(vote_num,TextSendMessage(text='投票者ゼロでした\uD83D\uDE22'))
        return

    data = redis.hvals('res_'+vote_num)
    answer_count = 0
    for value in data:
        answer_count += int(value)

    member_count = redis.scard(vote_num)
    if member_count > answer_count:
        push_all(vote_num,TextSendMessage(text='（棄権' + member_count - answer_count + '人）'))

    if answer_count == 1:
        three_str = '該当者なし'
        two_str = '該当者なし'
        data = redis.hkeys('res_'+vote_num)
        for value in data:
            name = getNameFromNum(vote_num,value)
            if isinstance(name,str):
                name = name.decode('utf-8')
        one_str = '全員一致で '+name+' さん（'+str(redis.hget('res_'+vote_num,value))+'票）でした！'
    else :
        result_list = generate_result_list(vote_num)
        one_str = result_list[0]
        two_str = result_list[1]
        three_str = result_list[2]

    push_all(vote_num,
        TextSendMessage(text='\uD83C\uDF1F\uD83C\uDF1F結果発表\uD83C\uDF1F\uD83C\uDF1F'))
    push_all(vote_num,
        TextSendMessage(text='3位は・・・'))
    time.sleep(RESULT_DISPLAY_TIMEOUT)
    push_all(vote_num,
        TextSendMessage(text=three_str))
    time.sleep(RESULT_DISPLAY_TIMEOUT)
    push_all(vote_num,
        TextSendMessage(text='2位は・・・'))
    time.sleep(RESULT_DISPLAY_TIMEOUT)
    push_all(vote_num,
        TextSendMessage(text=two_str))
    time.sleep(RESULT_DISPLAY_TIMEOUT)
    push_all(vote_num,
        TextSendMessage(text='\uD83C\uDF1F1位\uD83C\uDF1Fは・・・・'))
    time.sleep(RESULT_DISPLAY_TIMEOUT)
    push_all(vote_num,
        TextSendMessage(text=one_str))

def generate_result_list(number):
    result_value_list = redis.hvals('res_'+number)
    result_value_list.sort()
    result_value_list.reverse()

    max_val = result_value_list[0]
    ret_str = []
    added_count = 0
    loop_count = 0
    while added_count < 3:
        elem_str,count = generate_member_list_from_value(redis.hgetall('res_'+number),max_val,number)
        ret_str.append(elem_str)
        max_val = result_value_list[count]
        added_count += count
        loop_count += 1

    if loop_count == 1:
        ret_str.append('該当者なし')
        ret_str.append('該当者なし')
    elif loop_count == 2:
        ret_str.append('該当者なし')

    return ret_str


def generate_member_list_from_value(result_dict,objvalue,vote_num):
    sorted_dict = sorted(result_dict.items(), key=lambda x:x[1], reverse=True)
    count = 0
    ret_str = u''
    for key,value in sorted_dict:
        if value == objvalue:
            ret_str += getNameFromNum(vote_num,key)+'さん '
            count += 1
    ret_str += '(' + objvalue + '票)でした！'

    return (ret_str,count)

def push_all(vote_key,message):
    data = redis.smembers(vote_key)
    for value in data:
        line_bot_api.push_message(value,message)

def generateJoinButton():
    message = ImagemapSendMessage(
        base_url= HEROKU_SERVER_URL + 'images/button',
        alt_text='join',
        base_size=BaseSize(height=178, width=1040))
    actions=[]
    actions.append(MessageImagemapAction(
        text = 'join',
        area=ImagemapArea(
            x=0, y=0,
            width = BUTTON_ELEMENT_WIDTH,
            height = BUTTON_ELEMENT_HEIGHT)))
    actions.append(MessageImagemapAction(
        text = 'add',
        area=ImagemapArea(
            x=BUTTON_ELEMENT_WIDTH, y=0,
            width = BUTTON_ELEMENT_WIDTH * 2,
            height = BUTTON_ELEMENT_HEIGHT)))
    message.actions = actions
    return message

def generate_planning_poker_message(number):
    app.logger.info('[number] :' + number)
    data = redis.hgetall(number+'_member')
    generate_voting_target_image(number,data)

    count = len(data)
    if count < 3:
        vote_height = 260
        row_count = 1
    elif count < 7:
        vote_height = 520
        row_count = 2
    else:
        vote_height = 780
        row_count = 3

    message = ImagemapSendMessage(
        base_url= HEROKU_SERVER_URL + 'images/tmp/' + number,
        alt_text='vote board',
        base_size=BaseSize(height=vote_height, width=1040))
    actions=[]
    location=0
    for i in range(0, row_count):
        for j in range(0, 4):
            if location == count + 1: #最後
                actions.append(MessageImagemapAction(
                    text = u'#' + str(number).encode('utf-8') + u' 11',
                    area=ImagemapArea(
                        x=j * POKER_IMAGEMAP_ELEMENT_WIDTH,
                        y=i * POKER_IMAGEMAP_ELEMENT_HEIGHT,
                        width=(j + 1) * POKER_IMAGEMAP_ELEMENT_WIDTH,
                        height=(i + 1) * POKER_IMAGEMAP_ELEMENT_HEIGHT
                    )
                ))
            else:
                actions.append(MessageImagemapAction(
                    text = u'#' + str(number).encode('utf-8') + u' ' + str(location).encode('utf-8'),
                    area=ImagemapArea(
                        x=j * POKER_IMAGEMAP_ELEMENT_WIDTH,
                        y=i * POKER_IMAGEMAP_ELEMENT_HEIGHT,
                        width=(j + 1) * POKER_IMAGEMAP_ELEMENT_WIDTH,
                        height=(i + 1) * POKER_IMAGEMAP_ELEMENT_HEIGHT
                    )
                ))
                location+=1
    message.actions = actions
    return message
