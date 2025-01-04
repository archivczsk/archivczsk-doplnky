import re
import ast

def get_js_data(data, pattern=None):
    '''
    Extracts piece of javascript data from data based on pattern and converts it to python object
    If pattern is none, then data directly will be converted from javascript to python object
    '''
    if pattern:
        sources = re.compile(pattern, re.DOTALL)
        js_obj = sources.findall(data)[0]
    else:
        js_obj = data

    # remove all spaces not in double quotes
    js_obj = re.sub(r'\s+(?=([^"]*"[^"]*")*[^"]*$)', '', js_obj)

    # add double quotes around dictionary keys
    js_obj = re.sub(r'([{,]+)(\w+):', '\\1"\\2":', js_obj)

    # replace JS variables with python alternatives
    js_obj = re.sub(r'(["\']):undefined([,}])', '\\1:None\\2', js_obj)
    js_obj = re.sub(r'(["\']):null([,}])', '\\1:None\\2', js_obj)
    js_obj = re.sub(r'(["\']):NaN([,}])', '\\1:None\\2', js_obj)
    js_obj = re.sub(r'(["\']):true([,}])', '\\1:True\\2', js_obj)
    js_obj = re.sub(r'(["\']):false([,}])', '\\1:False\\2', js_obj)
    return ast.literal_eval(js_obj)
