import subprocess
out = subprocess.check_output(['netstat', '-ano'], text=True)
for line in out.splitlines():
    if ':8000' in line and 'LISTENING' in line:
        pid = line.strip().split()[-1]
        print('Killing', pid)
        subprocess.call(['taskkill', '/PID', pid, '/F'])
