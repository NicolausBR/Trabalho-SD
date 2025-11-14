import struct
import threading
import random
import sys
import time
import socket
import ipaddress
import os
from datetime import datetime

# Bibliotecas prompt_toolkit para interface amigável no terminal
from prompt_toolkit import PromptSession, print_formatted_text, HTML
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style

# Configurações do multicast
MULTICAST_GROUP = '224.1.1.1'
PORT = 5000

#Configurações de coordenador
COORDENADOR = None
INTERVALO_BATIMENTO = 1     # coordenador envia batimento a cada 1 segundo
LIMITE_BATIMENTO = 3       # se passar 3s sem ouvir o coordenador, há eleição
LISTA_NOS = []
ULTIMO_BATIMENTO = time.time()
TEMPO_STARTUP = 2.0 # tempo para aguardar o batimento inicial

# Informações do nó
NODE_ID = ''
NODE_NAME = ''
NODE_COLOR = ''

# Eventos para controle de threads
node_ready = threading.Event()
stop_event = threading.Event()

# Variáveis/estruturas para eleição
election_lock = threading.Lock()
respostas_eleicao = []        # lista de nos temporarios (responder_id, responder_name)
eleicao_em_andamento = False   # indica se este nó já iniciou eleição

# Sessão para entrada de usuário
session = PromptSession()

# Cores disponíveis para nomes
cores_disponiveis = {
    "preto": "ansibrightblack",
    "vermelho": "ansibrightred",
    "verde": "ansibrightgreen",
    "amarelo": "ansibrightyellow",
    "azul": "ansibrightblue",
    "magenta": "ansibrightmagenta",
    "ciano": "ansibrightcyan",
    "branco": "ansiwhite"
}

itens_coloridos = [f'<{cores_disponiveis[c]}>{c}</{cores_disponiveis[c]}>' for c in cores_disponiveis]
texto_colorido = ", ".join(itens_coloridos)

# --- Função para registrar logs ---
def registrar_log(evento):
    horario = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with open(f"logs/chat_log_{MULTICAST_GROUP}.txt", "a", encoding="utf-8") as f:
        f.write(f"[{horario}] {evento}\n")

# --- Função que escuta as mensagens multicast ---
def ouvir_multicast():
    global COORDENADOR
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((MULTICAST_GROUP, PORT))

    group = socket.inet_aton(MULTICAST_GROUP)
    interface = socket.inet_aton('0.0.0.0')
    mreq = struct.pack('4s4s', group, interface)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    # Buscar coordenador ao iniciar
    buscar_coordenador(sock)

    print(f"\nNó {NODE_ID} escutando no grupo {MULTICAST_GROUP}:{PORT}\n")
    node_ready.set()

    sock.settimeout(1.0)

    # Inicia thread para monitorar batimentos do coordenador
    threading.Thread(target=monitorar_coordenador, args=(sock,), daemon=True).start()

    while not stop_event.is_set():
        try:
            data, addr = sock.recvfrom(1024)
        except socket.timeout:
            continue
        
        msg = data.decode('utf-8')
        tratar_mensagem(msg, sock)

    sock.close()

# --- Função que envia mensagens multicast ---
def enviar_multicast():
    try:
      node_ready.wait()
      sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
      ttl = struct.pack('b', 1)
      sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)

      print('Digite a mensagem ("/sair" para encerrar, "/lista" para ver nós conectados caso seja coordenador):')
      while not stop_event.is_set():
            with patch_stdout():
              message = session.prompt("> ")

            if message.lower() == '/sair':
              enviar_mensagem("SAIR", sock)
              print(f"Encerrando Chat...")
              stop_event.set()
              break

            elif message.lower() == '/lista':
                if COORDENADOR and COORDENADOR[0] != NODE_ID:
                    with patch_stdout():
                        print_formatted_text(HTML("<ansiyellow>Somente o coordenador pode exibir a lista de nós.</ansiyellow>"))
                    continue
                with patch_stdout():
                    print("Nós conectados:")
                for no in LISTA_NOS:
                    print(f" - {no[1]} (ID: {no[0]})")
                continue
            
            enviar_mensagem("CHAT", sock, message)

      sock.close()
    except KeyboardInterrupt:
        enviar_mensagem("SAIR", sock, f"{NODE_ID}:{NODE_NAME}")
        print(f"Encerrando Chat via KeyboardInterrupt...")
        stop_event.set()

# --- Função para monitorar batimentos do coordenador ---
def monitorar_coordenador(sock):
    global ULTIMO_BATIMENTO, COORDENADOR
   
    iniciado_em = time.time()
    while not stop_event.is_set():
        time.sleep(0.5)

        # durante a janela inicial, não iniciar eleição
        if time.time() - iniciado_em < TEMPO_STARTUP:
            continue

        time.sleep(0.5)
        # Se eu for o coordenador eu apenas mando o batimento
        if COORDENADOR[0] == NODE_ID:
            enviar_mensagem("BATIMENTO", sock, "")
            continue
        if not (COORDENADOR and COORDENADOR[0] == NODE_ID):
            if time.time() - ULTIMO_BATIMENTO > LIMITE_BATIMENTO:
                with patch_stdout():
                    print_formatted_text(HTML("<ansibrightred>Nenhum batimento detectado. Iniciando eleição...</ansibrightred>"))
                # Inicia eleição em thread separada para não bloquear
                threading.Thread(target=eleger_coordenador, args=(sock,), daemon=True).start()
                # Dá um tempo para evitar disparos repetidos
                time.sleep(LIMITE_BATIMENTO)

# --- Função para enviar mensagens multicast ---
def enviar_mensagem(tipo, sock, msg = ""):
    try:
        mensagem_completa = f"{tipo}:{NODE_ID}:{NODE_NAME}:{NODE_COLOR}:{msg}"
        sock.sendto(mensagem_completa.encode('utf-8'), (MULTICAST_GROUP, PORT))

    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")

# --- Funções para o gerenciamento de coordenadores ---
def tratar_mensagem(msg, sock):
    try:
        global COORDENADOR, ULTIMO_BATIMENTO, LISTA_NOS, eleicao_em_andamento, respostas_eleicao
        tipo,id_no,nome_no,cor,conteudo = msg.split(":", 4)
        no_id = int(id_no.strip())

        if NODE_ID == COORDENADOR[0] and tipo not in ["BATIMENTO", "NOVA_LISTA", "BUSCA_COORDENADOR"]:
            write_log = f"{tipo}: {nome_no} (ID: {no_id}): {conteudo}"
            registrar_log(write_log)

        if no_id == NODE_ID:
            return
        if tipo == "BUSCA_COORDENADOR" and (COORDENADOR and COORDENADOR[0] == NODE_ID):
            while True:
                novo_id = random.randint(2, 10000)
                if all(n[0] != novo_id for n in LISTA_NOS) and novo_id != NODE_ID:
                    break
            
            registrar_log(f"{tipo}: {nome_no} (ID Temporário: {no_id})")
            resposta = f"ADD_NO:{NODE_ID}:{NODE_NAME}:{cor}:{novo_id},{no_id}:"
            LISTA_NOS.append((novo_id, nome_no))
            sock.sendto(resposta.encode('utf-8'), (MULTICAST_GROUP, PORT))

            return
        
        elif tipo == "NOVO_NO" and (id_no != NODE_ID):
            with patch_stdout():
                print_formatted_text(HTML(f"<{cor}>{nome_no}</{cor}> (ID: {id_no}) entrou no grupo!"))
            return
        
        elif tipo == "ELEICAO":
            # Se recebi uma eleição e meu ID é maior -> respondo
            write_log = f"ELEICAO: Iniciada por {nome_no} (ID: {no_id})"
            registrar_log(write_log)
            if NODE_ID > int(id_no):
                enviar_mensagem("ELEICAO_RESP", sock, "")
            return
                
        elif tipo == "ELEICAO_RESP":
            with election_lock:
                respostas_eleicao.append((int(id_no), nome_no))
            return
        
        elif tipo == "NOVO_COORDENADOR":
            COORDENADOR = (no_id, nome_no)
            ULTIMO_BATIMENTO = time.time()
            enviar_mensagem("NOVA_LISTA", sock, "")
            with election_lock:
                eleicao_em_andamento = False
                respostas_eleicao.clear()
            with patch_stdout():
                print_formatted_text(HTML(f"<ansibrightgreen>Novo coordenador: {nome_no} (ID: {no_id})</ansibrightgreen>"))
            return
        
        elif tipo == "BATIMENTO":
            ULTIMO_BATIMENTO = time.time()
            return
        
        elif tipo == "NOVA_LISTA" and (COORDENADOR and COORDENADOR[0] == NODE_ID):
            LISTA_NOS.append((no_id, nome_no))
            return
        
        elif tipo == "SAIR":
            sair_id = int(id_no)
            sair_nome = nome_no
            encontrado = False
            with patch_stdout():
                    print_formatted_text(HTML(f"Nó <{cor}>{sair_nome}</{cor}> (ID: {sair_id}) saiu do chat."))
            for no in LISTA_NOS:
                if str(no[0]) == str(sair_id) and no[1] == sair_nome:
                    LISTA_NOS.remove(no)
                    encontrado = True
                    break
            if (not encontrado) and COORDENADOR[0] == NODE_ID:
                with patch_stdout():
                    print_formatted_text(HTML(f"<ansired>Tentou remover nó inexistente: {sair_nome} (ID: {sair_id})</ansired>"))
            return
        elif tipo == "CHAT":
            with patch_stdout():
                print_formatted_text(HTML(f"<{cor}>{nome_no}:</{cor}> {conteudo.strip()}"))
        return
    
    except ValueError:
            with patch_stdout():
                print_formatted_text(HTML(f"<ansired>Mensagem mal formatada recebida: {msg}</ansired>"))
            return

# Buscar coordenador existente
def buscar_coordenador(sock):
    global COORDENADOR, NODE_ID, ULTIMO_BATIMENTO, LISTA_NOS
    id_temporario = random.randint(10001, 20000)

    def enviar_busca():
        mensagem = f"BUSCA_COORDENADOR:{id_temporario}:{NODE_NAME}:{NODE_COLOR}:"
        sock.sendto(mensagem.encode('utf-8'), (MULTICAST_GROUP, PORT))

    with patch_stdout():
        print_formatted_text(HTML("<ansiyellow>Buscando coordenador do Chat...</ansiyellow>"))
    enviar_busca()

    sock.settimeout(random.uniform(1.0, 3.0))

    try:
        while True:
            data, addr = sock.recvfrom(1024)
            msg = data.decode('utf-8')

            if msg.startswith("BATIMENTO"):
                enviar_busca()
                continue

            # Se alguém responder que é o coordenador
            if msg.startswith("ADD_NO"):
                partes = msg.split(":")
                if len(partes) >= 6:
                    ids = partes[4].split(",")
                    if len(ids) == 2 and ids[1] == str(id_temporario):
                        id_coord = partes[1]
                        nome_coord = partes[2]
                        meu_id = ids[0]
                        with patch_stdout():
                            print_formatted_text(HTML(f"<ansibrightgreen>Coordenador encontrado:</ansibrightgreen> {nome_coord} (ID: {id_coord})"))
                            print_formatted_text(HTML(f"<ansibrightred>ID recebido do coordenador:</ansibrightred> {meu_id}"))
                        COORDENADOR = (int(id_coord), nome_coord)
                        NODE_ID = int(meu_id)
                        ULTIMO_BATIMENTO = time.time()
                        enviar_mensagem("NOVO_NO", sock)
                        return
            
    except socket.timeout:
        # Se ninguém respondeu, este nó assume a liderança
        with patch_stdout():
            print_formatted_text(HTML("<ansibrightgreen>Nenhum coordenador encontrado. Assumindo liderança...</ansibrightgreen>"))
        NODE_ID = 1
        COORDENADOR = (NODE_ID, NODE_NAME)
        LISTA_NOS.append((NODE_ID, NODE_NAME))

        ULTIMO_BATIMENTO = time.time()
        with open(f"logs/chat_log_{MULTICAST_GROUP}.txt", "a", encoding="utf-8") as f:
            horario = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            f.write(f"\n--- Inicializando Chat de IP {MULTICAST_GROUP} [{horario}] ---\n")
        registrar_log(f"Coordenador Inicial: {NODE_NAME} (ID: {NODE_ID})")

        # Envia 3 batimentos imediatos para "anunciar" com redundância
        for _ in range(3):                
            enviar_mensagem("BATIMENTO", sock, "")
            time.sleep(0.2)               
                


# --- Função para eleição de coordenador usando bully-lite ---
def eleger_coordenador(sock, timeout=3.0):
    global eleicao_em_andamento, respostas_eleicao, COORDENADOR, NODE_ID, LISTA_NOS

    # Se já houver eleição em andamento, não inicia outra
    with election_lock:
        if eleicao_em_andamento:
            return
        eleicao_em_andamento = True
        respostas_eleicao.clear()

    # Envia mensagem de eleição (tipo ELEICAO)
    enviar_mensagem("ELEICAO", sock, "")

    # Aguarda respostas por `timeout` segundos (checando a cada 0.1s)
    espera = 0.0
    intervalo = 0.1
    while espera < timeout:
        time.sleep(intervalo)
        espera += intervalo
        with election_lock:
            # Se alguma resposta tiver ID maior que o meu, eu perco a eleição
            for resp_id, resp_name in respostas_eleicao:
                if int(resp_id) > NODE_ID:
                    # Houve resposta de ID maior — desiste e aguarda NOVO_COORDENADOR
                    with patch_stdout():
                        print_formatted_text(HTML(f"<ansiyellow>Recebi resposta de nó maior (ID {resp_id}). Aguardando novo coordenador...</ansiyellow>"))
                    eleicao_em_andamento = False
                    return

    # Se chegou aqui, nenhum nó respondeu com ID maior -> sou o líder
    COORDENADOR = (NODE_ID, NODE_NAME)
    with patch_stdout():
        print_formatted_text(HTML(f"<ansibrightgreen>Não houve respostas maiores — sou o novo coordenador (ID {NODE_ID})</ansibrightgreen>"))

    # anuncia novo coordenador para toda a rede
    enviar_mensagem("NOVO_COORDENADOR", sock, "")
    enviar_mensagem("BATIMENTO", sock, "")
    LISTA_NOS.append((NODE_ID, NODE_NAME))

    # marcar fim da eleição e limpar respostas
    with election_lock:
        eleicao_em_andamento = False
        respostas_eleicao.clear()

# --- Função para validar endereço IP multicast ---
def validar_ip_multicast(ip_str):
    try:
        ip = ipaddress.IPv4Address(ip_str)
        # Verifica se está na faixa de endereços multicast (224.0.0.0 – 239.255.255.255)
        if ip.is_multicast:
            return True
        else:
            print(f"Endereço {ip_str} não é multicast! Usando o padrão 224.1.1.200.")
            return False
    except ipaddress.AddressValueError:
        print(f"Endereço {ip_str} inválido! Usando o padrão 224.1.1.200.")
        return False
    
# --- Função principal ---
def chat():
    try:
        global NODE_NAME, NODE_COLOR, MULTICAST_GROUP
        
        # Cria diretório de logs se não existir (não envia para o git)
        os.makedirs("logs", exist_ok=True)

        NODE_NAME = input("Digite seu nome: ")
        print_formatted_text(HTML(f"Cores disponíveis: {texto_colorido}"))
        NODE_COLOR = input("Escolha a cor do seu nome: ").strip().lower()

        if NODE_COLOR not in cores_disponiveis:
            print("Cor inválida! Usando branco como padrão.")
            NODE_COLOR = "branco"
        NODE_COLOR = cores_disponiveis[NODE_COLOR]
        
        MULTICAST_GROUP = input("Digite o endereço multicast (padrão '224.1.1.1'): ") or '224.1.1.1'
        if not validar_ip_multicast(MULTICAST_GROUP):
            MULTICAST_GROUP = '224.1.1.1'

        t_listen = threading.Thread(target=ouvir_multicast, daemon=True)
        t_send = threading.Thread(target=enviar_multicast, daemon=True)
        t_listen.start()
        t_send.start()

        while not stop_event.is_set():
            time.sleep(0.5)

        print("Encerrando todas as threads...")
        t_listen.join(timeout=2)
        t_send.join(timeout=2)
        with patch_stdout():
            print_formatted_text(HTML("<ansibrightgreen>Programa finalizado com segurança.</ansibrightgreen>"))
        sys.exit(0)
    
    except Exception as e:
        print(f"Erro inesperado: {e}")
        stop_event.set()
        with patch_stdout():
            print_formatted_text(HTML("<ansibrightgreen>Programa finalizado com segurança.</ansibrightgreen>"))
        sys.exit(1)

    except KeyboardInterrupt:
        print(f"\nEncerrando o Chat via KeyboardInterrupt...")
        stop_event.set()
        with patch_stdout():
            print_formatted_text(HTML("<ansibrightgreen>Programa finalizado com segurança.</ansibrightgreen>"))
        sys.exit(0)

if __name__ == "__main__":
    chat()