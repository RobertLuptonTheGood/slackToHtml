#!/usr/bin/env python
import datetime
import glob
import html
import json
import os
import re
import textwrap

class User:
    def __init__(self, userId, userDict):
        self._dict = userDict

        self.userId = userId
        self.name = userDict.get('display_name', "")
        if self.name == "":
            self.name = userDict['real_name']

        self.image_url = userDict.get('image_72')  # URL to look up avatar image

    def __str__(self):
        return self.name if self.name else ""


class Msg:
    def __init__(self, msgDict):
        msg = None; del msg
        self._dict = msgDict

        self.ts = msgDict['ts']
        self.thread_ts = msgDict.get('thread_ts')
        self.date = datetime.datetime.fromtimestamp(float(msgDict['ts']))

        if msgDict['type'] not in ["message"]:
            print(msg); raise RuntimeError("")

        global users
        if msgDict['type'] == 'message' and msgDict.get('subtype') == "bot_message":
            self.user = User(msgDict.get('bot_id', "BID"),
                             dict(display_name=msgDict.get('username', "???")))
        elif msgDict['type'] == 'message' and msgDict.get('subtype') == "channel_join":
            self.user = User('channel_join',
                             dict(display_name=msgDict.get('user_name', None)))
        else:
            self.user = users[msgDict['user']]

        if 'blocks' in msgDict:
            self.blocks = msgDict['blocks']
        else:
            self.blocks = [dict(elements=[dict(elements=[dict(type='text',
                                                               text=msgDict['text'])])])]
        self.files = msgDict.get('files', [])
            
    def __repr__(self):
        return str(self.blocks)

    @staticmethod
    def get_text(el):
        text = el['text']

        if el.get('style', {}).get('code'):
            text = f"<code>{html.escape(text)}</code>"
        else:
            while True:
                mat = re.search(r"<@([^>]+)>", text)
                if not mat:
                    break

                rawUserId = mat.group(1)
                userId = re.sub(r"\|.*$", "", rawUserId) # userId can be e.g. @U3A2P4FEH|cloomis
                text = re.sub(f"<@{rawUserId}>", f"@{users[userId]}", text)

            text = html.escape(text)
            text = text.replace('\n', '<BR>')

        return text

    def getOutput(self, width=100):
        output = []
        for block in self.blocks:
            for el in block['elements']:
                preformatted = False
                if el.get('type') == 'rich_text_preformatted':
                    preformatted = True
                    width = None  # disable wrapping

                    output.append("<PRE>")
                elif el.get('type') == 'rich_text_list':
                    pass
                else:
                    if el.get('type') not in [None, 'rich_text_section']:
                        print(el['type'])
                        import pdb; pdb.set_trace() 

                for el2 in el['elements']:
                    if el2['type'] == 'text':
                        output.append(self.get_text(el2))
                    elif el2['type'] == 'rich_text_section':
                        for el3 in el2['elements']:
                            output.append(self.get_text(el3))

                        output.append("</PRE>")
                    elif el2['type'] == 'channel':
                        channel = f"#{channels[el2['channel_id']]}"
                        output.append(channel)
                    elif el2['type'] == 'emoji':  # e.g. {'type': 'emoji', 'name': 'slightly_smiling_face'}
                        emoji = f":{el2['name']}:"
                        output.append(emoji)
                    elif el2['type'] == 'link':
                        url = el2['url']
                        link = f"<a href='{url}'>{url}</a>"
                        output.append(link)
                    elif el2['type'] == 'user':   # e.g. {'type': 'user', 'user_id': 'UA82J1WP3'}
                        user = users.get(el2['user_id'], el2['user_id'])
                        user = f"@{user}"

                        output.append(user)
                    else:
                        raise RuntimeError(f"Complain to RHL: {el2}")

                if preformatted: 
                    output.append("<PRE>")
                        
        if width and False:
            output = textwrap.wrap(" ".join(output), width)

        if self.files:
            output.append("<UL style='list-style: none;'>")
            for f in self.files:
                thumb = "thumb_360"

                if f.get('mode') == "tombstone":
                    output.append("(This file was deleted)")
                    continue

                if thumb in f:
                    nameStr = f"<IMG SRC='{f['thumb_360']}'></IMG>"
                else:
                    nameStr = f['name']

                output.append(f"<LI><A HREF='{f['url_private_download']}'>{nameStr}</A></LI>")

            output.append("</UL>")
                
        return output

    def __str__(self):
        return "\n".join(self.getOutput())

def format_msg(msg, indent=""):
    """Format a single message, possibly with an indent at the start of each line"""
    
    output = []
    indent = ""
    output.append("<DT>")

    timeStr = msg.date.strftime('%a %Y-%m-%d %I:%M%p')
    img = f"<img width=16 height=16 src={msg.user.image_url}></img>" if msg.user.name else ""
    output.append(f"{img}  {str(msg.user):25s}  {timeStr}")

    output.append("</DT><DD>")

    outputStr = "\n".join(msg.getOutput())
    for ci, co in [('’', "'"), 
                   ('…', '...'),
                   ('…', '...'),
                   ('“', '"'),
                   ('”', '"'),
                   (' ', '_'),
                   ('—', '-'),
    ]:
        outputStr = outputStr.replace(ci, co)

    output.append(outputStr)
    
    output.append("</DD>")

    return indent + f"\n{indent}".join(output)

def formatSlackArchive(rootDir, channelList=None, outputDir=None, projectName="PFS"):
    """Format a slack archive to be human readable

    If channelList is not None, it's a list of channels to process (otherwise
    we process all of them)

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

        if channelList is not None and channelName not in channelList:
            continue

        msgs[channelName] = []
        threads[channelName] = {}

        inputFiles[channelName] = sorted(glob.glob(os.path.join(rootDir, channelName, "*.json")))
        for fileName in inputFiles[channelName]:
            with open(fileName) as fd:
                data = json.load(fd)

            for msg in data:
                if msg.get('subtype') in ["file_comment"]:
                    continue

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
        with open(os.path.join(outputDir, f"{channel}.html"), "w") as fd:
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

                    print(format_msg(msg), file=fd)

                    if len(msgs_thread) > 1:
                        print("<DT></DT><DD><DL>", file=fd)

                    for m in msgs_thread[1:]:
                        print(format_msg(m, "|\t"), file=fd)

                    if len(msgs_thread) > 1:
                        print("</DD></DL>", file=fd)

                else:
                    print(format_msg(msg), file=fd)

                print('', file=fd)

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
    parser.add_argument('--channels', '-c', nargs="+", help="Only process these channels")
    parser.add_argument('--project', '-p', help="Name of project; default PFS", default="PFS")

    args = parser.parse_args()

    formatSlackArchive(args.rootDir, channelList=args.channels,
                       outputDir=args.outputDir, projectName=args.project)
