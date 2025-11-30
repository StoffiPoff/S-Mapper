import sys
from collections import deque

path = sys.argv[1]
text = open(path, 'r', encoding='utf-8').read()
stack = deque()
pairs = {'(':')','[':']','{':'}'}
line = 1
col = 0
for i,ch in enumerate(text):
    col += 1
    if ch == '\n':
        line += 1
        col = 0
    if ch in '([{':
        stack.append((ch,line,col))
    elif ch in ')]}':
        if not stack:
            print('Unmatched closing', ch, 'at', line, col)
            sys.exit(2)
        top, l, c = stack.pop()
        if pairs[top] != ch:
            print('Mismatched', top, 'at', l, c, 'vs', ch, 'at', line, col)
            sys.exit(2)
if stack:
    for s,l,c in stack:
        print('Unmatched opening', s, 'at', l, c)
    sys.exit(2)
print('All balanced')
