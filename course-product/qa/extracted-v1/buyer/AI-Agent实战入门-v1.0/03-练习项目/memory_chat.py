"""Project 2: SQLite persistence with separate sessions and bounded context."""
import argparse
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from common import CourseError, completion, print_json


@contextmanager
def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        with conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL)''')
            yield conn
    finally:
        conn.close()


def history(path, session):
    with connect(path) as conn:
        rows = conn.execute('SELECT role, content FROM messages WHERE session = ? ORDER BY id', (session,)).fetchall()
    return [{'role': r, 'content': c} for r, c in rows]


def recent_context(messages, limit=6, char_budget=6000):
    """Select complete recent user/assistant pairs; not a token counter."""
    selected = []
    used = 0
    for i in range(len(messages) - 2, -1, -2):
        pair = messages[i:i+2]
        cost = sum(len(m['content']) for m in pair)
        if len(selected) + 2 > limit or used + cost > char_budget:
            break
        selected = pair + selected
        used += cost
    return selected


def chat(path, session, text, online=False, request_fn=completion):
    if not session.strip() or len(session) > 100:
        raise CourseError('会话名称必须为 1 到 100 个字符。')
    if not text.strip() or len(text) > 3000:
        raise CourseError('输入必须为 1 到 3000 个字符。')
    old = history(path, session)
    if online:
        messages = [{'role': 'system', 'content': '你是学习助手。只记得提供给你的近期对话；如果上下文缺失请说明，不要猜测。'}]
        messages += recent_context(old)
        messages.append({'role': 'user', 'content': text})
        answer = request_fn(messages).get('content')
        if not isinstance(answer, str) or not answer.strip():
            raise CourseError('模型未返回可保存的文本；本轮未入库。')
    else:
        previous = next((m['content'] for m in reversed(old) if m['role'] == 'user'), None)
        answer = '离线回放：上一次用户输入为“' + previous + '”。' if previous else '离线回放：这是本会话第一次输入。'
    # Save the pair atomically only after obtaining a complete answer.
    with connect(path) as conn:
        conn.executemany('INSERT INTO messages(session, role, content) VALUES (?, ?, ?)',
                         [(session, 'user', text), (session, 'assistant', answer)])
    return {'mode': 'online' if online else 'offline', 'session': session,
            'answer': answer, 'message_count': len(old) + 2}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='runtime/learning.sqlite3')
    parser.add_argument('--session', default='learner')
    parser.add_argument('--message')
    parser.add_argument('--history', action='store_true')
    parser.add_argument('--online', action='store_true')
    args = parser.parse_args()
    try:
        if args.history: print_json(history(args.db, args.session))
        elif args.message: print_json(chat(args.db, args.session, args.message, args.online))
        else: parser.error('请提供 --message 或 --history。')
    except (CourseError, sqlite3.Error, OSError) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
