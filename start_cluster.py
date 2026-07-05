import subprocess
import time
import sys
from config import NODES

def start_cluster():
    processes = []
    try:
        print("Iniciando cluster...")
        for node_id in NODES:
            p = subprocess.Popen([sys.executable, "node.py", "--id", str(node_id)])
            processes.append(p)
            print(f"Nó {node_id} iniciado na porta {5000 + node_id}")
        
        # Manter o script rodando enquanto os processos existirem
        for p in processes:
            p.wait()
            
    except KeyboardInterrupt:
        print("\nEncerrando cluster...")
        for p in processes:
            p.terminate()

if __name__ == "__main__":
    start_cluster()
