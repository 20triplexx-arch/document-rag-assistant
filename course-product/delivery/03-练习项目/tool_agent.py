"""Project 1: tool contracts, validation, observations, and a bounded loop."""
import argparse
import json
import math
from common import CourseError, completion, print_json

SCHEMA = {'type': 'function', 'function': {
    'name': 'calculate', 'description': '对两个数字做加减乘除；返回程序计算的结果。',
    'parameters': {'type': 'object', 'properties': {
        'operation': {'type': 'string', 'enum': ['add', 'subtract', 'multiply', 'divide']},
        'a': {'type': 'number'}, 'b': {'type': 'number'}},
        'required': ['operation', 'a', 'b'], 'additionalProperties': False}}}


def calculate(arguments):
    if not isinstance(arguments, dict) or set(arguments) != {'operation', 'a', 'b'}:
        return {'ok': False, 'error': '参数必须且只能包含 operation、a、b。'}
    op, a, b = arguments['operation'], arguments['a'], arguments['b']
    if op not in ['add', 'subtract', 'multiply', 'divide']:
        return {'ok': False, 'error': '不支持的运算。'}
    for value in (a, b):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return {'ok': False, 'error': 'a 和 b 必须是数字，不能是布尔值或字符串。'}
        if abs(value) > 1e12 or not math.isfinite(value):
            return {'ok': False, 'error': '数值必须有限且绝对值不超过 10^12。'}
    if op == 'divide' and b == 0:
        return {'ok': False, 'error': '除数不能为零。'}
    if op == 'add': result = a + b
    elif op == 'subtract': result = a - b
    elif op == 'multiply': result = a * b
    else: result = a / b
    return {'ok': True, 'result': result}


def execute_tool(name, raw_arguments):
    if name != 'calculate':
        return {'ok': False, 'error': '未知工具。'}
    try:
        arguments = json.loads(raw_arguments)
    except (TypeError, ValueError):
        return {'ok': False, 'error': '工具参数不是有效 JSON。'}
    return calculate(arguments)


def run_online(question, request_fn=completion, max_rounds=4):
    messages = [
        {'role': 'system', 'content': '你是教学计算助手。算术必须调用 calculate。遇到工具错误应解释或纠正参数；不要编造结果。'},
        {'role': 'user', 'content': question}]
    trace = []
    total_calls = 0
    for step in range(max_rounds):
        message = request_fn(messages, [SCHEMA])
        calls = message.get('tool_calls') or []
        if not calls:
            if not trace:
                raise CourseError('模型没有执行工具，不能把算术答复作为已完成的计算。')
            if not isinstance(message.get('content'), str) or not message['content'].strip():
                raise CourseError('模型没有返回答案。')
            return {'mode': 'online', 'answer': message['content'], 'trace': trace, 'model_calls': step + 1}
        if len(calls) + total_calls > 8:
            raise CourseError('工具调用次数超过教学上限 8，停止执行。')
        ids = []
        for call in calls:
            if not isinstance(call, dict) or not isinstance(call.get('id'), str) or not call['id']:
                raise CourseError('模型工具调用缺少 ID，停止执行。')
            if call['id'] in ids or not isinstance(call.get('function'), dict):
                raise CourseError('工具调用 ID 重复或格式错误。')
            ids.append(call['id'])
        messages.append(message)
        for call in calls:
            fn = call['function']
            observation = execute_tool(fn.get('name'), fn.get('arguments'))
            trace.append({'tool': fn.get('name'), 'observation': observation})
            messages.append({'role': 'tool', 'tool_call_id': call['id'],
                             'content': json.dumps(observation, ensure_ascii=False)})
            total_calls += 1
    raise CourseError(f'达到模型调用上限 {max_rounds}，停止执行。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--online', action='store_true', help='显式联网，产生模型 API 费用')
    parser.add_argument('--question', default='先计算 18 乘以 7，再加 9。')
    parser.add_argument('--operation', choices=['add', 'subtract', 'multiply', 'divide'], default='multiply')
    parser.add_argument('--a', type=float, default=18)
    parser.add_argument('--b', type=float, default=7)
    args = parser.parse_args()
    try:
        if args.online:
            print_json(run_online(args.question))
        else:
            result = calculate({'operation': args.operation, 'a': args.a, 'b': args.b})
            print_json({'mode': 'offline', 'note': '参数由命令行给定，不调用模型。', 'tool': 'calculate', 'observation': result})
            if not result['ok']: raise SystemExit(2)
    except CourseError as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
