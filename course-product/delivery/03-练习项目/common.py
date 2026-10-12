"""Independent teaching code. Python 3.12 standard library only."""
import json
import os
import socket
import urllib.error
import urllib.request


class CourseError(Exception):
    """A readable configuration, transport, or response error."""


def completion(messages, tools=None):
    """Call DeepSeek only when a demo explicitly selects --online.

    No key is written to disk; no automatic retry creates extra paid calls.
    The function returns the assistant message, preserving tool-call IDs.
    """
    key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
    model = os.environ.get('DEEPSEEK_MODEL', '').strip()
    if not key:
        raise CourseError('请在当前终端设置 DEEPSEEK_API_KEY；离线模式不需要密钥。')
    if not model:
        raise CourseError('请设置 DEEPSEEK_MODEL 为控制台可用模型，例如 deepseek-flash。')
    payload = {'model': model, 'messages': messages, 'stream': False,
               'max_tokens': 1200, 'thinking': {'type': 'disabled'}}
    if tools:
        payload['tools'] = tools
    request = urllib.request.Request(
        'https://api.deepseek.com/chat/completions',
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
        method='POST')
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        guidance = {400: '检查模型、消息格式和参数。', 401: '检查密钥。',
                    402: '检查账户余额。', 429: '请求过多，请稍后手动重试。'}
        raise CourseError(f'接口返回 HTTP {exc.code}。' + guidance.get(exc.code, '稍后手动重试并检查服务状态。')) from None
    except (urllib.error.URLError, TimeoutError, socket.timeout):
        raise CourseError('联网请求失败或超时；检查网络，程序不会自动重试。') from None
    except (ValueError, TypeError):
        raise CourseError('接口未返回可解析的 JSON。') from None
    try:
        choice = result['choices'][0]
        if choice.get('finish_reason') == 'length':
            raise CourseError('模型输出达到长度限制，本次结果未完整生成。')
        message = choice['message']
        if not isinstance(message, dict) or message.get('role') != 'assistant':
            raise KeyError('message')
        if not message.get('content') and not message.get('tool_calls'):
            raise KeyError('empty message')
        return message
    except (KeyError, IndexError, TypeError):
        raise CourseError('接口响应缺少可用的 assistant 消息。') from None


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))
