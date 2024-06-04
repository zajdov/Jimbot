"""
utils.py
"""


def concatenate(args: tuple[any, ...]) -> str:
    return ' '.join([str(a).replace('\n', '') for a in args if a != '\n'])
