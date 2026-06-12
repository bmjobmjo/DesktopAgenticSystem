import sys
path = r'D:\Works\GenericAgent\DesktopAgenticSystem\apps\whatsapp_bridge\headless\daemon.js'
with open(path, 'r', encoding='utf8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'await whatsappLib.sendMessage' in line:
        lines[i] = line.replace('await whatsappLib.sendMessage', 'sendResult = await whatsappLib.sendMessage')

# find the line with "Move to backup on success"
for i, line in enumerate(lines):
    if '// Move to backup on success' in line:
        lines.insert(i, "        if (typeof sendResult !== 'undefined' && sendResult && sendResult.success === false) {\n            throw new Error(sendResult.error || 'Failed to send via Baileys');\n        }\n")
        break

# define let sendResult; right before the first if (attPath)
for i, line in enumerate(lines):
    if 'if (attPath) {' in line and 'whatsappLib.sendMessage' in lines[i+1]:
        lines.insert(i, "        let sendResult;\n")
        break

with open(path, 'w', encoding='utf8') as f:
    f.writelines(lines)
print('Patched successfully')
