import hashlib
import base64
import os.path
import re
import traceback

import requests
import threading
import time
import json
from datetime import datetime
import pytz

from ..xunfei.xunfei_spark_bot import XunFeiBot, Context, Reply, ContextType, logger
from ..xunfei.xunfei_spark_bot import reply_map, queue_map, ReplyType
# from voice.baidu.baidu_voice import BaiduVoice
from voice.ali.ali_voice import AliVoice
from voice.azure.azure_voice import AzureVoice
from .notebot_image import NotebotImage

from dotenv import load_dotenv

try:
    load_dotenv('.env')
except Exception as e:
    traceback.print_exc()

oov_answer_text = '''
你这样说，我理解不了。
看的我一脸懵，都开始怀疑我的智商了。
你想表达什么意思？
你这是在考我吗？
不明白你的意思。
坦白说，我没看懂什么意思。
搞不清楚你在说什么。
你说什么？
我有点不理解你的意思。
我不知道该怎么回答。
'''
oov_answers = [line for line in oov_answer_text.split('\n') if line]

_esman_manage_api = os.environ.get('esman_manage_api', 'http://localhost:6043/manage')
_esman_search_api = os.environ.get('esman_search_api', 'http://localhost:6043/search')


class NoteBot(XunFeiBot, NotebotImage):
    def __init__(self):
        super().__init__()
        self.esman_manage_api = _esman_manage_api
        self.esman_search_api = _esman_search_api
        self.voiceToText = AliVoice().voiceToText
        self.textToVoice = AzureVoice().textToVoice

    def parse_query(self, query, context: Context = None) -> str:
        if context.type == ContextType.VOICE:
            if "Recognition" in context:
                out_text = context["Recognition"]
            else:
                out_text = self.voiceToText(query).content
        elif context.type == ContextType.IMAGE:
            out_text = '计划OCR识别文字和大模型介绍图片，敬请期待！'
        elif context.type == ContextType.VIDEO:
            out_text = '计划解析视频，敬请期待！'
        elif context.type == ContextType.FILE:
            out_text = '计划解析文件，敬请期待！'
        elif context.type == ContextType.TEXT:
            out_text = query  # context['Content']
        else:
            out_text = '我知道这是个{}，但是...{}'.format(
                context.type, oov_answers[int(time.time()) % len(oov_answers)])
        tun = context["msg"].to_user_id  # ["ToUserName"]
        tuni = context["msg"].to_user_nickname
        fun = context["msg"].from_user_id  # ["FromUserName"]
        funi = context["msg"].from_user_nickname
        uun = context["msg"].other_user_id  # ["User"]["UserName"]
        unni = context["msg"].other_user_nickname  # ["User"]["NickName"]
        sdn = context["msg"].self_display_name
        auni = context["msg"].actual_user_nickname
        logger.info(f'context["msg"]: {context["msg"]}')
        if context["msg"].is_group and context["msg"].is_at:
            # user_id = context["msg"].actual_user_id
            nickname = context["msg"].actual_user_nickname
        else:
            nickname = context["msg"].from_user_nickname
            if not nickname:  # 微信公众号nickname是None
                nickname = context["msg"].from_user_id

        # user_id = base64.urlsafe_b64encode(hashlib.md5(nickname.encode('utf-8')).digest()).decode()[:-2]
        user_id = hashlib.md5(nickname.encode('utf-8')).hexdigest()
        return out_text, user_id

    def reply(self, query, context: Context = None) -> Reply:
        if context.type == ContextType.IMAGE_CREATE:
            # 生成图片
            ok, retstring = self.create_img(query, 0)
            reply = None
            if ok:
                reply = Reply(ReplyType.IMAGE_URL, retstring)
            else:
                reply = Reply(ReplyType.ERROR, retstring)
            return reply

        query, receiver = self.parse_query(query, context)
        contents = []
        if context.type in [ContextType.TEXT, ContextType.VOICE, ContextType.IMAGE, ContextType.VIDEO,
                            ContextType.FILE]:
            logger.info("[NoteBot] query={}, receiver={}".format(query, receiver))
            session_id = context["session_id"]
            request_id = self.gen_request_id(session_id)
            reply_map[request_id] = ""
            recall_flag = query.strip().endswith('？？？') \
                          or re.search(r'(提取|回忆)(一下|记录|记忆|信息|内容)\W*$', query.strip()) \
                          or re.search(r'^\W*(提取|回忆)(一下|记录|记忆|信息|内容)', query.strip())
            note_flag = query.strip().endswith('！！！') \
                        or re.search(r'(记录|记忆)(一下|信息|内容)\W*$', query.strip()) \
                        or re.search(r'^\W*(记录|记忆)(一下|信息|内容)', query.strip())

            if recall_flag:
                # 提取信息
                _index = f'notebot-{receiver}'
                response = requests.post(self.esman_search_api,
                                         params=dict(_index=_index, query=query, topn=100, threshold=0))
                if response.status_code == 200:
                    contents = ['\n'.join(dt['_source']['content']) for dt in response.json()]
                    contents = [w.strip() for w in contents if w.strip()]
                    content = '\n\n'.join(contents)
                    prompt = f'请根据下面内容回答问题。\n' \
                             f'内容：\n{content}\n\n问题：\n{query}\n'
                else:
                    prompt = query
                session = self.sessions.session_query(prompt, session_id)
                threading.Thread(target=self.create_web_socket, args=(session.messages[-1:], request_id)).start()

            elif note_flag:
                prompt = f'请简要回答下面问题，回答30字以内。\n\n{query}'
                session = self.sessions.session_query(prompt, session_id)
                threading.Thread(target=self.create_web_socket, args=(session.messages[-1:], request_id)).start()

            elif query.strip().endswith('。。。') or re.search(r'(多轮对话|前文|上下文)\W*$', query.strip()):
                prompt = query
                session = self.sessions.session_query(prompt, session_id)
                threading.Thread(target=self.create_web_socket, args=(session.messages[-10:], request_id)).start()
            else:
                prompt = query
                session = self.sessions.session_query(prompt, session_id)
                threading.Thread(target=self.create_web_socket, args=(session.messages[-1:], request_id)).start()
            depth = 0
            time.sleep(0.1)
            t1 = time.time()
            usage = {}
            while depth <= 300:
                try:
                    data_queue = queue_map.get(request_id)
                    if not data_queue:
                        depth += 1
                        time.sleep(0.1)
                        continue
                    data_item = data_queue.get(block=True, timeout=0.1)
                    if data_item.is_end:
                        # 请求结束
                        del queue_map[request_id]
                        if data_item.reply:
                            reply_map[request_id] += data_item.reply
                        usage = data_item.usage
                        break

                    reply_map[request_id] += data_item.reply
                    depth += 1
                except Exception as e:
                    depth += 1
                    continue
            t2 = time.time()
            logger.info(f"[XunFei-API] response={reply_map[request_id]}, time={t2 - t1}s, usage={usage}")
            self.sessions.session_reply(reply_map[request_id], session_id, usage.get("total_tokens"))
            if note_flag:
                _index = f'notebot-{receiver}'
                content = query.strip()  # [:-3]
                _reply = f'记录信息成功！\n{reply_map[request_id]}'

            elif recall_flag:
                _index = f'notebot-{receiver}'
                content = ''
                ref = ''.join(['{}. {}\n'.format(i, w.strip().replace('\n', '\t'))
                               for i, w in enumerate(contents[:5], 1)])
                _reply = f'{reply_map[request_id]}\n\n参考信息：\n{ref}'

            else:
                _index = f'notebot-{receiver}'
                content = ''
                _reply = reply_map[request_id]

            # 记录信息
            _source = context["msg"].__dict__
            timestamp = str(datetime.now(tz=pytz.timezone('Asia/Shanghai'))).replace(' ', 'T')
            _source.update(ctype=str(_source["ctype"]), query=query, answer=_reply, prompt=prompt, timestamp=timestamp)
            # print(_source)
            # {'_rawmsg': VoiceMessage({'ToUserName': 'gh_4ce45b3d405f', 'FromUserName': 'o3e9G04LpkY2mIS1dS4TVVxWpARo', 'CreateTime': '1706966222', 'MsgType': 'voice', 'MediaId': 'YlJjzl-F3A8xYHzkGeYuFy7bXc44aScqZPjt05ttCPfKQg0qxs9kVmJoXYF4_HpCAluURAeJwmmDh1FOn0WPcQ', 'Format': 'amr', 'MsgId': '7331364098866675712', 'Recognition': None}),
            # 'msg_id': 7331364098866675712, 'create_time': 1706966222, 'is_group': False, 'ctype': 'VOICE',
            # 'content': 'mnt/media/YlJjzl-F3A8xYHzkGeYuFy7bXc44aScqZPjt05ttCPfKQg0qxs9kVmJoXYF4_HpCAluURAeJwmmDh1FOn0WPcQ.amr',
            # '_prepare_fn': <function WeChatMPMessage.__init__.<locals>.download_voice at 0x7f366033bf40>, 'from_user_id': 'o3e9G04LpkY2mIS1dS4TVVxWpARo', 'to_user_id': 'gh_4ce45b3d405f', 'other_user_id': 'o3e9G04LpkY2mIS1dS4TVVxWpARo', '_prepared': True,
            # 'query': '记录一下，这个不知道改了多少遍了，改了至少也十遍了吧。这个语音识别还有技术机器人。', 'answer': '好的，已经记录下来了。\n\n参考信息：\n', 'prompt': '请简要回答下面问题，回答30字以内。\n\n记录一下，这个不知道改了多少遍了，改了至少也十遍了吧。这个语音识别还有技术机器人。'}

            # {'_rawmsg': TextMessage({'ToUserName': 'gh_4ce45b3d405f', 'FromUserName': 'o3e9G04LpkY2mIS1dS4TVVxWpARo', 'CreateTime': '1706967141', 'MsgType': 'text', 'Content': '你是谁呢，记录一下', 'MsgId': '24437893681409676'}),
            # 'msg_id': 24437893681409676, 'create_time': 1706967141, 'is_group': False, 'ctype': 'TEXT',
            # 'content': '你是谁呢，记录一下', 'from_user_id': 'o3e9G04LpkY2mIS1dS4TVVxWpARo', 'to_user_id': 'gh_4ce45b3d405f', 'other_user_id': 'o3e9G04LpkY2mIS1dS4TVVxWpARo',
            # 'query': '你是谁呢，记录一下', 'answer': '您好，我是科大讯飞研发的认知智能大模型，我的名字叫讯飞星火认知大模型。我可以和人类进行自然交流，解答问题，高效完成各领域认知智能需求。\n\n参考信息：\n', 'prompt': '请简要回答下面问题，回答30字以内。\n\n你是谁呢，记录一下'}

            if _source['ctype'] != 'TEXT':
                if os.path.isfile(_source['content']) and os.path.getsize(_source['content']) <= 1024 ** 2:
                    logger.info(f'[NoteBot] media <{_source["content"]}> send to knowledge base')
                    media = base64.a85encode(open(_source['content'], 'rb').read()).decode()
                    _source['media'] = media

            data = dict(_index=_index,
                        _id=request_id,
                        content=content,
                        _source=json.dumps({k: v for k, v in
                                            _source.items() if isinstance(v, (str, int, float, bool))},
                                           ensure_ascii=False))
            flag = requests.post(self.esman_manage_api, params=data)
            if flag.status_code == 200:
                logger.info(
                    f"[NoteBot-API] esman manage flag={flag.json()}, _index={data['_index']}, _id={data['_id']}")
            else:
                logger.error(
                    f"[NoteBot-API] esman manage flag={flag.content.decode()}, _index={data['_index']}, _id={data['_id']}")

            reply = Reply(ReplyType.TEXT, _reply)
            del reply_map[request_id]
            return reply
        else:
            reply = Reply(ReplyType.ERROR, "Bot不支持处理{}类型的消息".format(context.type))
            return reply
