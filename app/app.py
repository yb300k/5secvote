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
mapping = {"0":"0", "1":"1", "2":"2", "3":"3", "4":"5", "5":"8", "6":"13", "7":"20", "8":"40", "9":"?", "10":"∞", "11":"Soy"}

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

    line_bot_api.reply_message(
        event.reply_token, TextSendMessage(text='こんにちわ\uD83D\uDE04\n'+
        'みんなでせーのでタイミングを合わせて参加ボタンを押してね\uD83D\uDE03'))

    line_bot_api.push_message(
        sourceId,generateJoinButton())

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    text = event.message.text
    sourceId = getSourceId(event.source)
    matcher = re.match(r'^#(\d+) (.+)', text)

    if text == 'join':#メンバ集め・・・今後要検討
        join_mutex = Mutex(redis, JOIN_MUTEX_KEY_PREFIX+ sourceId)
        join_mutex.lock()
        if join_mutex.is_lock():
            number = str(redis.get('maxVoteKey')).encode('utf-8')
            if redis.sismember(number,sourceId) == 0:
                redis.sadd(number,sourceId)
                redis.hset(sourceId,'current',number)
        else:
            number = str(redis.incr('maxVoteKey')).encode('utf-8')
            if redis.sismember(number,sourceId) == 0:
                redis.sadd(number,sourceId)
                redis.hset(sourceId,'current',number)
            time.sleep(JOIN_MUTEX_TIMEOUT)
            push_all(number,generate_planning_poker_message(number))
            join_mutex.unlock()
    elif text == 'add':
        pass

    elif matcher is not None:
        number = matcher.group(1)
        value = matcher.group(2)
        current = redis.hget(sourceId,'current').encode('utf-8')
        if current != number:
            line_bot_api.reply_message(
                event.reply_token, TextSendMessage(text='投票板が古かった？もう一度お願いします！'))
            line_bot_api.push_message(
                sourceId,generate_planning_poker_message(current))
            return

        if redis.hget(sourceId,'voted') == 'Y':
            line_bot_api.reply_message(
                event.reply_token, TextSendMessage(text='すでに投票済です・・結果集計をお待ちください')
            return
        else:
            redis.hset(sourceId,'voted','Y')

        poker_mutex = Mutex(redis, POKER_MUTEX_KEY_PREFIX+ sourceId)
        vote_mutex = Mutex(redis, VOTE_MUTEX_KEY_PREFIX  + sourceId)

        vote_key = 'res_' + number

        vote_mutex.lock()
        if vote_mutex.is_lock():
            redis.hincrby(vote_key, value)
            time.sleep(VOTE_MUTEX_TIMEOUT)

            push_result_message(number)
            #結果発表後の結果クリア
            res_list = redis.hkeys(vote_key)
            for value in res_list.itervalues():
                 redis.hdel(vote_key,value)
            member_list = redis.smembers(number)
            for value in member_list:
                redis.hset(value,'voted','N')

            vote_mutex.unlock()
            poker_mutex.release()
        else:
            redis.hincrby(vote_key, value)

def push_result_message(vote_key):
    push_all(vote_key,
        TextSendMessage(text='3位は'))
    time.sleep(RESULT_DISPLAY_TIMEOUT)
    push_all(vote_key,
        TextSendMessage(text='2位は'))
    time.sleep(RESULT_DISPLAY_TIMEOUT)
    push_all(vote_key,
        TextSendMessage(text='1位は・・・・'))
    time.sleep(RESULT_DISPLAY_TIMEOUT)
    push_all(vote_key,
        TextSendMessage(text='でした！'))

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
            x=0,
            y=0,
            width = BUTTON_ELEMENT_WIDTH,
            height = BUTTON_ELEMENT_HEIGHT)))
    actions.append(MessageImagemapAction(
        text = 'add',
        area=ImagemapArea(
            x=BUTTON_ELEMENT_WIDTH,
            y=0,
            width = BUTTON_ELEMENT_WIDTH * 2,
            height = BUTTON_ELEMENT_HEIGHT)))
    message.actions = actions
    return message

def genenate_voting_result_message(key):
    data = redis.hgetall(key)
    tmp = generate_voting_result_image(data)
    buttons_template = ButtonsTemplate(
        title='ポーカー結果',
        text='そろいましたか？',
        thumbnail_image_url=HEROKU_SERVER_URL + 'images/tmp/' + tmp + '/result_11.png',
        actions=[
            MessageTemplateAction(label='もう１回', text='プラポ')
    ])
    template_message = TemplateSendMessage(
        alt_text='結果', template=buttons_template)
    return template_message

def generate_planning_poker_message(number):
    app.logger.info('[number] :' + number)
    data = redis.smembers(number)
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
