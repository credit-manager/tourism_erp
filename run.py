import uvicorn, os, sys, threading, socket, subprocess, time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

def _free_port(port=8000):
    for _ in range(3):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            r = s.connect_ex(("127.0.0.1", port))
            s.close()
            if r != 0:
                return True
        except:
            return True
        try:
            out = subprocess.check_output(
                f'netstat -ano | findstr ":{port} "',
                shell=True, text=True, timeout=5,
            )
            for line in out.strip().splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and parts[1].endswith(f":{port}"):
                    pid = int(parts[4])
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
                    time.sleep(1)
        except:
            pass
    return False

if __name__ == "__main__":
    try:
        _free_port(8000)
        from tunnel_manager import start as start_tunnel
        threading.Thread(target=start_tunnel, daemon=True).start()
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
    except Exception as e:
        print(f"\n ERROR: {e}\n")
        input("\nPress Enter to exit...")
