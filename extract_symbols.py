import re

# Read the Connector_Generic library
with open(r'C:\Users\Anirudh\AppData\Local\Programs\KiCad\10.0\share\kicad\symbols\Connector_Generic.kicad_sym', 'r') as f:
    content = f.read()

# Find Conn_01x15
pattern = r'(\(symbol "Conn_01x15"[\s\S]*?\n\t\(embedded_fonts no\)\n\t\))'
match = re.search(pattern, content)
if match:
    print('Found Conn_01x15')
    print(match.group(1)[:500])
else:
    print('Conn_01x15 not found')

# Find Conn_01x06
pattern = r'(\(symbol "Conn_01x06"[\s\S]*?\n\t\(embedded_fonts no\)\n\t\))'
match = re.search(pattern, content)
if match:
    print('Found Conn_01x06')
    print(match.group(1)[:500])
else:
    print('Conn_01x06 not found')