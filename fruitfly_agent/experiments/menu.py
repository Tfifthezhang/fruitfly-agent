"""Select an operation; inspection and configuration selection perform no work."""


def select_operation(*, read=input, write=print):
    operations = ('eval', 'improvement', 'rsi')
    write('FruitFlyAgent experiments\n1. Eval\n2. Improvement\n3. RSI\nEnter to exit')
    choice = read('Operation: ').strip()
    if not choice:
        return None
    if choice not in {'1', '2', '3'}:
        raise ValueError('choose an operation number from 1 to 3')
    operation = operations[int(choice) - 1]
    write('1. Check configuration\n2. Run (model calls may incur charges)\n3. List runs\nEnter to return')
    action = read('Action: ').strip()
    if not action:
        return None
    if action not in {'1', '2', '3'}:
        raise ValueError('choose an action number from 1 to 3')
    return operation, ('check', 'run', 'list')[int(action) - 1]
