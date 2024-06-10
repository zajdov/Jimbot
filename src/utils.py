
def concatenate(args: tuple[any, ...]) -> str:
    return ' '.join([str(a).replace('\n', '') for a in args if a != '\n'])


def handle(func) -> any:
    func._is_handler = True    
    return func
