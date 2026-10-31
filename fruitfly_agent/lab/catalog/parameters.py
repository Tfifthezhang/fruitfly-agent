"""Owner-declared public parameter paths and flat installer projections."""


def encode_parameters(definition, values):
    if not definition.parameter_paths:
        return dict(values)
    result={}
    for name,value in values.items():
        path=definition.parameter_paths[name]
        current=result
        parts=path.split('.')
        for key in parts[:-1]:current=current.setdefault(key,{})
        current[parts[-1]]=value
    return result


def decode_parameters(definition, value):
    if not definition.parameter_paths:
        return dict(value)
    inverse={path:name for name,path in definition.parameter_paths.items()}
    result={}
    def visit(values,prefix=''):
        if not isinstance(values,dict):raise ValueError('component parameters require grouped fields')
        for key,item in values.items():
            path=prefix+'.'+key if prefix else key
            if path in inverse:result[inverse[path]]=item
            elif isinstance(item,dict) and any(p.startswith(path+'.') for p in inverse):visit(item,path)
            else:raise ValueError('unknown component parameter: '+path)
    visit(value)
    return result
