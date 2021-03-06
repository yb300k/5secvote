# -*- coding: utf-8 -*-

import os

POKER_MUTEX_TIMEOUT = 20
POKER_MUTEX_KEY_PREFIX = 'MUTEX_POCKER_'
POKER_IMAGEMAP_ELEMENT_WIDTH = 260
POKER_IMAGEMAP_ELEMENT_HEIGHT = 260
POKER_IMAGE_FILENAME =  'pp-{0}.png'

JOIN_MUTEX_TIMEOUT = 3
JOIN_MUTEX_KEY_PREFIX = 'JOIN_VOTE_'
VOTE_MUTEX_TIMEOUT = 5
VOTE_MUTEX_KEY_PREFIX = 'MUTEX_VOTE_'

JOIN_IMAGE_FILENAME = 'join-{0}.png'

IMG_PATH = os.path.join(os.path.dirname(__file__), 'static', 'planning_poker')
TMP_ROOT_PATH = os.path.join(os.path.dirname(__file__), 'static', 'tmp')

START_IMAGE_FILENAME = 'start3.png'
EXIT_IMAGE_FILENAME = 'start3.png'
FONT_FILENAME = 'ipaexg.ttf'

BG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'static', 'planning_poker', 'vote_background.png')
MESSAGE_END_POKER = '#{0}の投票は終了してまーす'
MESSAGE_INVALID_VOTE = '#{0}の投票はないですよ。手入力した？'

HEROKU_SERVER_URL = 'https://fivesecvote.herokuapp.com/'

BUTTON_ELEMENT_WIDTH = 520
BUTTON_ELEMENT_HEIGHT = 178

RESULT_DISPLAY_TIMEOUT = 1
