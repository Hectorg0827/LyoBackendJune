with open("/Users/hectorgarcia/Desktop/LyoBackendJune/lyo_app/enhanced_main.py", "r") as f:
    text = f.read()

if "OS ENVIRON AT BOOTSTRAP START" in text:
    lines = text.splitlines()
    new_lines = []
    skip = False
    for line in lines:
        if "OS ENVIRON AT BOOTSTRAP START" in line:
            new_lines.pop() # remove import os
            skip = True
        if skip and "========================" in line:
            skip = False
            continue
        if skip:
            continue
        new_lines.append(line)
    
    with open("/Users/hectorgarcia/Desktop/LyoBackendJune/lyo_app/enhanced_main.py", "w") as f:
        f.write("\n".join(new_lines) + "\n")
