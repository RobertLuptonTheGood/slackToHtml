#!/usr/bin/env python
import datetime
import glob
import html
import json
import os
import re

class User:
    def __init__(self, userId, userDict):
        self._dict = userDict

        self.userId = userId
        self.name = userDict['display_name']
        if self.name == "":
            self.name = userDict['real_name']

        self.image_url = userDict.get('image_72')  # URL to look up avatar image

    def __str__(self):
        return self.name


class Msg:
    def __init__(self, msgDict):
        msg = None; del msg
        self._dict = msgDict

        self.ts = msgDict['ts']
        self.thread_ts = msgDict.get('thread_ts')
        self.date = datetime.datetime.fromtimestamp(float(msgDict['ts']))

        if msgDict['type'] not in ["message"]:
            print(msg); raise RuntimeError("")
            
        if msgDict['type'] == 'message' and msgDict.get('subtype') == "bot_message":
            self.user = User(msgDict['bot_id'],
                                 dict(display_name=msgDict.get('username', "???")))
        else:
            self.user = User(msgDict['user'],
                                 msgDict.get('user_profile', dict(display_name="???")))

        if 'blocks' in msgDict:
            self.payload = msgDict['blocks']
        else:
            self.payload = [dict(elements=[dict(elements=[dict(type='text', text=msgDict['text'])])])]
            
    def __repr__(self):
        return str(self.payload)

    def getOutput(self, width=100, writeHtml=True):
        output = []
        for block in self.payload:
            for el in block['elements']:
                preformatted = False
                if el.get('type') == 'rich_text_preformatted':
                    preformatted = True
                    width = None  # disable wrapping

                    if writeHtml:                        
                        output.append("<PRE>")

                for el2 in el['elements']:
                    if el2['type'] == 'text':
                        text = el2['text']

                        if el2.get('style') and el2.get('style').get('code'):
                            text = text.replace('&', '\177')
                            text = f"<code>{html.escape(text)}</code>" if writeHtml else f"`{text}`"
                            text = text.replace('\177', '&')
                        elif writeHtml:
                            text = html.escape(text)

                        output.append(text)
                    elif el2['type'] == 'rich_text_section':
                        for el3 in el2['elements']:
                            text = el3['text']
                            if el3.get('style') and el3.get('style').get('code'):
                                if '&' in text:
                                    raise RuntimeError('XX')

                                text = text.replace('&', '\177')
                                text = f"<code>{html.escape(text)}</code>" if writeHtml else f"`{text}`"
                                text = text.replace('\177', '&')
                            elif writeHtml:
                                text = html.escape(text)

                            output.append(text)

                        if writeHtml:
                            output.append("</PRE>")
                    elif el2['type'] == 'channel':
                        channel = f"#{channels[el2['channel_id']]}"
                        output.append(channel)
                    elif el2['type'] == 'emoji':  # e.g. {'type': 'emoji', 'name': 'slightly_smiling_face'}
                        emoji = f":{el2['name']}:"
                        output.append(emoji)
                    elif el2['type'] == 'link':
                        url = el2['url']
                        link = f"<a href='{url}'>{url}</a>" if writeHtml else f"<{url}>"
                        output.append(link)
                    elif el2['type'] == 'user':   # e.g. {'type': 'user', 'user_id': 'UA82J1WP3'}
                        user = users.get(el2['user_id'], el2['user_id'])
                        user = f"@{user}"

                        output.append(user)
                    else:
                        raise RuntimeError(f"Complain to RHL: {el2}")

                if preformatted and writeHtml: 
                    output.append("<PRE>")
                        
        import textwrap
        if width:
            output = textwrap.wrap(" ".join(output), width)

        return output

    def __str__(self):
        return "\n".join(self.getOutput())

def format_msg(msg, indent="", writeHtml=True):
    """Format a single message, possibly with an indent at the start of each line"""
    
    output = []
    if writeHtml:
        indent = ""
        output.append("<DT>")

    timeStr = msg.date.strftime('%a %Y-%m-%d %I:%M%p')
    if writeHtml:
        output.append(f"<img width=16 height=16 src={msg.user.image_url}></img>  {msg.user.name:25s}  {timeStr}")
    else:
        output.append(f"From: {msg.user.name:25s}  {timeStr}")

    if writeHtml:
        output.append("</DT>")
        output.append("<DD>")

    outputStr = "\n".join(msg.getOutput(writeHtml=writeHtml))
    if writeHtml:
        for ci, co in [('’', "'"), 
                       ('…', '...'),
                       ('…', '...'),
                       ('“', '"'),
                       ('”', '"'),
                       (' ', ' '),
                      ]:
            outputStr = outputStr.replace(ci, co)

    output.append(outputStr)
    
    if writeHtml:
        output.append("</DD>")
    else:
        output.append(f"------------------")

    return indent + f"\n{indent}".join(output)

def formatSlackArchive(rootDir, outputDir=None, writeHtml=True, projectName="PFS"):
    """Format a slack archive to be human readable

    The layout is expected to be like:
       rootdir/channel1/date1.json
                        date2.json
               channel2/date1.json
                        date2.json
               ...

    and the output is
        outputDir/channel1.html
                  channel2.html
                  ...

    (or .txt if writeHtml is False)
    """

    if outputDir == None:
        outputDir = rootDir

    if not os.path.isdir(outputDir):
        os.makedirs(outputDir)
    #
    # Start by defining all channels and users
    #
    with open(os.path.join(rootDir, "channels.json")) as fd:
        data = json.load(fd)

    global channels
    channels = {}
    for msg in data:
        channels[msg['id']] = msg['name']

    with open(os.path.join(rootDir, "users.json")) as fd:
        data = json.load(fd)

    global users
    users = {}
    for msg in data:
        user = User(msg['id'], msg['profile'])
        users[user.userId] = user
    #
    # Then read all the messages
    #
    global msgs, threads
    msgs = {}
    threads = {}
    inputFiles = {} 
    for channel in glob.glob(os.path.join(rootDir, "*")):
        if not os.path.isdir(channel):  # e.g. older channel.txt outputs
            continue

        channelName = os.path.split(channel)[-1]
        msgs[channelName] = []
        threads[channelName] = {}

        inputFiles[channelName] = sorted(glob.glob(os.path.join(rootDir, channelName, "*.json")))
        for fileName in inputFiles[channelName]:
            with open(fileName) as fd:
                data = json.load(fd)

            for msg in data:
                msg = Msg(msg)
                msgs[channelName].append(msg)

                if msg.thread_ts:
                    if msg.thread_ts not in threads[channelName]:
                        threads[channelName][msg.thread_ts] = []
                    threads[channelName][msg.thread_ts].append(msg)
    #
    # Ready for output
    #
    for channel in msgs:
        if len(inputFiles[channel]) == 0:
            continue

        dates = [os.path.splitext(os.path.split(f)[1])[0] for f in inputFiles[channel]]
        title = f"{projectName} slack archives {channel} {dates[0]}---{dates[-1]}"
        with open(os.path.join(outputDir, f"{channel}.{'html' if writeHtml else 'txt'}"), "w") as fd:
            if writeHtml:
                print(f"""
    <HTML>
    <HEAD>
      <TITLE>{title}</TITLE>
    </HEAD>

    <BODY>
    <H3>{title}</H3>

    <DL>""", file=fd)

            for msg in msgs[channel]:
                if msg.thread_ts in threads[channel]:
                    msgs_thread = threads[channel][msg.thread_ts]
                    if msg != msgs_thread[0]:
                        continue   # already processed

                    print(format_msg(msg, writeHtml=writeHtml), file=fd)

                    if writeHtml and len(msgs_thread) > 1:
                        print("<DT></DT><DD><DL>", file=fd)

                    for m in msgs_thread[1:]:
                        print(format_msg(m, "|\t", writeHtml=writeHtml), file=fd)

                    if writeHtml and len(msgs_thread) > 1:
                        print("</DD></DL>", file=fd)

                else:
                    print(format_msg(msg, writeHtml=writeHtml), file=fd)

                print('', file=fd)

            if writeHtml:
                print(f"""
    </DL>
    </BODY>
    </HTML>""", file=fd)

# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
           

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="")

    parser.add_argument('rootDir', type=str, help="Directory containing directories with json")
    parser.add_argument('--outputDir', '-o', help="Directory to write files; default <rootDir>")
    parser.add_argument('--project', '-p', help="Name of project; default PFS", default="PFS")
    parser.add_argument('--text', action="store_true", help="Dump data as text files?", default=False)

    args = parser.parse_args()

    formatSlackArchive(args.rootDir, args.outputDir, writeHtml=not args.text, projectName=args.project)
