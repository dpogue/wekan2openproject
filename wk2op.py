#!/usr/bin/python3

from urllib.request import urlopen, Request
from urllib.error import HTTPError
from urllib.parse import urlencode
from base64 import b64encode
import json
import os
import sys

RUN = True

try:
    TOKEN = os.environ['OP_API_TOKEN']
    OP_URL = os.environ['OP_API_ENDPOINT']
    OP_ID = os.environ['OP_PROJECT_ID']
except KeyError as e:
    raise SystemExit('Missing required environment variable ' + str(e))


def fetch(url, method='GET', body=None, headers={}):
    if not 'Content-Type' in headers:
        headers['Content-Type'] = 'application/json'

    if not 'Authorization' in headers:
        token = b64encode(bytes('apikey:%s' % TOKEN, 'utf-8')).decode('ascii')
        headers['Authorization'] = 'Basic %s' % token

    if not url.startswith('http'):
        url = OP_URL + url

    data = None
    if body:
        data = body.encode('utf8')

    req = Request(url, data, headers, method=method)

    try:
        resp_obj = urlopen(req)
    except HTTPError as e:
        print(e)
        err = e.read()
        raise SystemError(err)

    resp = json.load(resp_obj)
    resp_obj.close()
    return resp



if len(sys.argv) < 2:
    raise SystemExit('Usage: wk2op.py <path_to_wekan_json>')

wekan_data = json.load(open(sys.argv[1], 'r'))

if not wekan_data['_format'] == 'wekan-board-1.0.0':
    raise SystemExit('Invalid Wekan board data')


# Hardcoded sadness because dynamically fetching this is unfeasible :(
version = '/api/v3/versions/8'

wk2op_user_map = {
    'N54tnXfaWQGLFEahb': '/api/v3/users/5',
    'QMFskvFgCzGZcmurb': '/api/v3/users/9',
    'aYGB9PxY89dXxEQT5': '/api/v3/users/11',
    'oMDvEoTZquEPqSzbi': '/api/v3/users/11'
}

wk2op_status_map = {
    'Pool': 'New',
    'Ready': 'New',
    'Doing': 'In progress',
    'Waiting': 'On hold',
    'Done': 'Closed'
}

op_statuses = { st['name'] : st['_links']['self']['href'] for st in fetch('/statuses')['_embedded']['elements'] }
statuses = { st['_id'] : op_statuses[wk2op_status_map[st['title']]] for st in wekan_data['lists'] }


# Loop over the cards on the Wekan board
for card in wekan_data['cards']:
    work_project = {
        "subject": card['title'],
        "startDate": card['createdAt'][:10],
        "_links": {
            "status": {
                "href": statuses[card['listId']]
            },
            "version": {
                "href": version
            }
        }
    }

    if 'description' in card and len(card['description']) > 0:
        work_project['description'] = { 'raw': card['description'] }

    if 'dueAt' in card and card['dueAt']:
        work_project['dueDate'] = card['dueAt'][:10]

    if len(card['members']) > 0:
        assignee = card['members'][0]
        if assignee in wk2op_user_map:
            work_project['_links']['assignee'] = { 'href': wk2op_user_map[assignee] }


    if RUN:
        resp = fetch(('/projects/%s/work_packages?notify=false' % OP_ID), method='POST', body=json.dumps(work_project))

        pkgid = resp['id']
        print(resp['_links']['self'])
    else:
        print(json.dumps(work_project))
        pkgid = 'foo'


    # Handle comments (I don't think I can preserve the author though...)
    for comment in wekan_data['comments']:
        if comment['cardId'] != card['_id']:
            continue

        comment_author = wk2op_user_map[comment['userId']][8:].replace('s/', '#')
        comment_date = comment['createdAt'][:16].replace('T', ' at ')

        comm_data = {
            'comment': {
                'format': 'markdown',
                'raw': '%s posted on %s:\n> %s' % (comment_author, comment_date, comment['text'].replace('\n', '\n> '))
            }
        }

        if RUN:
            resp = fetch(('/work_packages/%s/activities?notify=false' % pkgid), method='POST', body=json.dumps(comm_data))
            print('\t%s' % resp['_links']['self'])
        else:
            print('\t%s' % json.dumps(comm_data))

    # Handle checklist items nested inside the card as subtasks
    checklist = next((chklst for chklst in wekan_data['checklists'] if chklst['cardId'] == card['_id']), None)
    if checklist is not None:
        for check in wekan_data['checklistItems']:
            if check['checklistId'] != checklist['_id']:
                continue

            status = op_statuses['Closed'] if check['isFinished'] else op_statuses['New']
            subtask = {
                'subject': check['title'],
                '_links': {
                    'status': {
                        'href': status
                    },
                    'parent': {
                        'href': '/api/v3/work_packages/%s' % pkgid
                    }
                }
            }


            if RUN:
                resp = fetch(('/projects/%s/work_packages?notify=false' % OP_ID), method='POST', body=json.dumps(subtask))
                href = resp['_links']['self']
                print(href)
            else:
                print('\t%s' % json.dumps(subtask))

    if not RUN:
        print()
    #break
