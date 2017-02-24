# -*- coding:utf-8 -*-

from flask import Flask, request, abort, send_from_directory, url_for
import errno
import os
from random import randint
import redis

from const import *

app = Flask(__name__)
app.config.from_object('config')
redis = redis.from_url(app.config['REDIS_URL'])

def make_static_dir(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

def getSourceId(source):
    sourceType = source.type
    if sourceType == 'user':
        return source.user_id
    elif sourceType == 'group':
        return source.group_id
    elif sourceType == 'room':
        return source.room_id
    else:
        raise NotFoundSourceError()

class NotFoundSourceError(Exception):
    pass

entry = {
    '0':'+75+75',
    '1':'+313+75',
    '2':'+551+75',
    '3':'+789+75',
    '4':'+75+304',
    '5':'+313+304',
    '6':'+551+304',
    '7':'+789+304',
    '8':'+75+533',
    '9':'+313+533',
    '10':'+551+533',
    '11':'+789+533',
}

def generate_voting_target_image(number,data):

    for i in range(1, 11):
        display_name = redis.hget(data[i-1],'name')
        path = os.path.join(TMP_ROOT_PATH,i+'.png')
        cmd = _letter2img_cmd(display_name,path)
        os.system(cmd)

    path = os.path.join(TMP_ROOT_PATH, number)
    make_static_dir(path)

    cmd = _montage_cmd(path,len(data))
    os.system(cmd)

    for size in [240, 300, 460, 700]:
        resize_cmd = _resize_cmd(path, size)
        os.system(resize_cmd)
    return number


def _letter2img_cmd(letters,out_file):
    font_file = os.path.join(TMP_ROOT_PATH,FONT_FILENAME)
    cmd = []
    cmd.append('convert -font')
    cmd.append(font_file)
    cmd.append('-size 200x160 -gravity center')
    cmd.append('label:'+letters)
    cmd.append(out_file)

    return ' '.join(cmd)

def _montage_cmd(path,count):
    out_file = os.path.join(path,'vote-1040.png')

    cmd = []
    cmd.append('montage')
    for i in range(0,12):
        elem_file = os.path.join(TMP_ROOT_PATH,i+'png')
        cmd.append(elem_file)
    cmd.append('-tile 4x3 -resize 100% -geometry +0+0')
    cmd.append(out_file)

    return cmd

def _resize_cmd(path, size):
    before = path + '/vote-1040.png'
    after = path + '/vote-' + str(size) + '.png'
    cmd = []
    cmd.append('convert -resize')
    cmd.append(str(size) + 'x')
    cmd.append(before)
    cmd.append('-quality 00')
#    cmd.append('-colors 8')
    cmd.append(after)
    return ' '.join(cmd)

def generate_voting_result_image(data):
    number, path = _tmpdir()
    for i in range(0, 12):
        cmd = _generate_cmd(i, data, path)
        os.system(cmd)
    resize_cmd = 'mogrify -resize 50% -unsharp 2x1.4+0.5+0 -colors 65 -quality 100 -verbose ' + path + '/result_11.png'
    os.system(resize_cmd)
    return number

def _generate_cmd(position, data, tmp):
    if position is 0:
        bg_file = BG_FILE_PATH
        out_file = os.path.join(tmp, 'result_0.png')
    else:
        bg_file = os.path.join(tmp, 'result_' + str(position-1) + '.png')
        out_file = os.path.join(tmp, 'result_' + str(position) + '.png')
    value = data[str(position)] if data.has_key(str(position)) else str(0)
    cmd = []
    cmd.append('composite -gravity northwest -geometry')
    cmd.append(entry[str(position)])
    cmd.append('-compose over')
    cmd.append(os.path.join(IMG_PATH, 'vote_' + value + '.png'))
    cmd.append(bg_file)
    cmd.append(os.path.join(tmp, out_file))
    return ' '.join(cmd)

def _tmpdir():
    number = str(randint(1000, 9999))
    path = os.path.join(TMP_ROOT_PATH, number)
    make_static_dir(path)
    return (number, path)
