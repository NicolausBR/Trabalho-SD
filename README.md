# Trabalho Final - Sistemas Distribuídos 2025/2
### By Nicolas Pereira Ribeiro - https://github.com/NicolausBR/Trabalho-SD

## Tema
Implementação de um **Chat P2P (Peer-to-Peer)** com **eleição de coordenador** e **comunicação via multicast**. O sistema de mensagens instantâneas distribuído **(sem servidor central)**
onde os nós da rede podem enviar e receber mensagens em tempo real, além de que ele deve
ser resiliente a falhas de nós e **capaz de se reorganizar automaticamente** em caso de
desconexões.

## Estrutura dos nós
Os nós podem ser coodernadores (1 por vez), e esses coordenadores são responsáveis por associar um ID para cada um dos nós que entram na rede.
Cada nó possui um ID, nome e cor personalizada.

### Threads
Os nós funcionam a partir de 4 threads para uma execução assíncrona, podendo realizar outras tarefas sem a necessidade de pausar a execução, sendo elas as seguintes:

- **`ouvir_multicast`**: Responsável por receber mensagens na rede multicast, sendo a responsável por inicializar um nó, chamando o coordenado ao ser instanciado;
- **`enviar_multicast`**: Responsável por enviar as mensagens na rede multicast, que agurada o nó terminar a configuração de listen para ser executada;
- **`monitorar_coordenador`**: Responsável por enviar e receber as mensagens de "HEARTBEAT" do coordenador, inciando a thread de eleição caso esse sinal não seja recebido;
- **`eleger_coordenador`**: Instanciada para controlar o fluxo do processo de eleição, a fim de evitar que várias eleições ocorram ao mesmo tempo.


## Mensagens

As mensagens são enviadas pela thread eviar_multicast utilizando a função enviar_mensagem(), que possuem o seguinte formato:

- `TIPO`:`NODE_ID`:`NODE_NAME`:`NODE_COLOR`:`DADOS`

    - **`TIPO`**: Header responsável por definir como a mensagem será tratada na função  tratar_mensagem();

    - **`NODE_ID`**: ID do nó que enviou a mensagem;

    - **`NODE_NAME`**: Nome do nó que enviou a mensagem;
    
    - **`NODE_COLOR`**: Cor personalizada do nó que aparece em algumas mensagens;

    - **`DADOS`**: Campo opcional com dados adicionais, como a mensagem em si que será exibida no terminal.

### Tipos de Mensagens

As mensagens são divididas nos seguintes tipos:

- **`BUSCA_COORDENADOR`**: Usada quando um nó novo entra na rede e deseja descobrir quem é o coordenador atual.  
O coordenador responde atribuindo um **novo ID aleatório** ao nó.

- **`ADD_NO`**: Mensagem enviada pelo coordenador em resposta à `BUSCA_COORDENADOR`.  
Define o ID do novo nó e o adiciona à lista de nós conhecidos.

- **`NOVO_NO`**: Enviada quando um novo nó entra na rede, notificando todos os participantes.

- **`CHAT`**: Mensagem de texto normal enviada entre nós para o chat.

- **`BATIMENTO`**: Mensagem periódica enviada pelo coordenador para sinalizar que ele está ativo.  
Se os outros nós não receberem o batimento dentro de um tempo limite, uma **eleição é iniciada**.

- **`ELEICAO`**: Mensagem usada para iniciar o processo de eleição.  
Qualquer nó pode iniciá-la caso detecte ausência de batimentos.

    - Um nó **responde com `ELEICAO_RESP`** se possuir um ID **maior** que o nó que iniciou a eleição.  
    - Isso garante que o nó com maior ID será o novo coordenador.

- **`ELEICAO_RESP`**: Enviada como resposta à mensagem de eleição, informando que há nós com ID superior.

- **`NOVO_COORDENADOR`**: Mensagem enviada pelo nó que venceu a eleição, anunciando-se como o novo coordenador. Os demais nós atualizam sua referência de coordenador e reiniciam o monitoramento.

- **`NOVA_LISTA`**: Enviada pelo  novo coordenador aos nós para **sincronizar a lista completa de participantes** da rede.

- **`SAIR`**: Enviada quando um nó sai da rede.  
O coordenador remove o nó da lista local e exibe a saída no terminal de todos os nós.

## Processo de Eleição

O processo de eleição segue uma variação do **Algoritmo do Eleitor Bully (Bully Election Algorithm)**:

1. Quando um nó detecta que o coordenador não responde (`BATIMENTO` ausente), ele **envia uma mensagem `ELEICAO`**.
2. Todos os nós com **ID maior** que o do nó iniciador respondem com `ELEICAO_RESP`.
3. Se o nó **não receber nenhuma resposta** dentro de um tempo limite, ele **se declara coordenador** e envia `NOVO_COORDENADOR`.
4. Todos os nós **atualizam o novo coordenador** e voltam ao estado normal de operação.

## Log de Mensagens

O chat possui um sistema de **log** que registra as mensagens trocadas entre os nós, **com exceção** das mensagens dos tipos `BATIMENTO` e `NOVA_LISTA`, a fim de evitar que o log se torne excessivamente grande e complexo.

Além disso, apenas o **coordenador** é responsável por registrar as mensagens no log, **exceto** durante o processo de **eleição**, quando todos os nós participantes podem registrar eventos relevantes.


## Iniciando o Projeto

O projeto utiliza um **ambiente virtual (venv)** para as bibliotecas, portanto **não há necessidade de instalação manual**.

Para iniciar o ambiente virtual e o projeto, utilize um dos comandos abaixo:

### Linux
```bash
source sd/bin/activate
python3 p2p.py
```


### Windons
```bash
sd\Scripts\activate
python3 p2p.py
```



