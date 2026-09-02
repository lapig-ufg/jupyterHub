# LAPIG JupyterHub — Health Check

Serviço de monitoramento dos containers de usuário do JupyterHub. Roda como um container Docker dentro do mesmo stack Swarm, monitorando todos os containers `jupyter-*` a cada minuto e registrando saúde e erros em arquivos de log estruturados.

Eventos monitorados:
- **OOM Kill** — container morto pelo kernel por exceder o limite de memória
- **Crash / exit code anormal** — container encerrou de forma inesperada
- **Alta memória** — container acima do threshold configurado (padrão: 90%)
- **Saúde periódica** — CPU, RAM e uptime de cada container ativo

---

## Sumário

- [Estrutura de arquivos](#estrutura-de-arquivos)
- [Como subir o serviço](#como-subir-o-serviço)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Estrutura de logs](#estrutura-de-logs)
- [Exemplos de log](#exemplos-de-log)

---

## Estrutura de arquivos

```
health-check/
├── Dockerfile          # Imagem do serviço de monitoramento
├── monitor.py          # Script principal
├── requirements.txt    # Dependência: biblioteca docker
└── README.md           # Este arquivo
```

---

## Como subir o serviço

### 1. Build da imagem

A partir da raiz do repositório:

```bash
cd health-check/
docker build -t lapig/jupyterhub-monitor:v1 .
```

### 2. Adicionar ao docker-compose.yml do stack

Adiciona o serviço `monitor` dentro do `docker-compose.yml` que já contém o `jupyterhub` e o `glances`:

```yaml
services:

  # ... serviços existentes (jupyterhub, glances) ...

  monitor:
    image: lapig/jupyterhub-monitor:v1
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - /home/lapig/applications/service/jupyterHub/logs:/logs
    environment:
      - MONITOR_INTERVAL=60
      - MEM_WARN_PERCENT=90
      - LOGS_BASE=/logs
    networks:
      - web_lapig_sci2
    deploy:
      replicas: 1
      placement:
        constraints:
          - node.role == manager
      restart_policy:
        condition: on-failure
```

> O socket Docker é montado em **somente-leitura** (`:ro`) — o monitor observa os containers, nunca os gerencia.

### 3. Criar as pastas de log no host

Execute uma vez antes de subir o stack, para garantir que as pastas existam com as permissões corretas:

```bash
mkdir -p /home/lapig/applications/service/jupyterHub/logs/jupyterhub
mkdir -p /home/lapig/applications/service/jupyterHub/logs/users
```

As pastas por usuário (ex: `logs/users/aurilio/`) são criadas automaticamente pelo monitor no primeiro spawn de cada usuário.

### 4. Fazer o deploy do stack

```bash
cd docker/
docker stack deploy -c docker-compose.yml jupyterhub-sci2
```

### 5. Verificar que está rodando

```bash
docker service ls | grep monitor
docker service logs jupyterhub-sci2_monitor -f
```

A saída esperada na inicialização:

```
[2026-09-02 20:03:45] LAPIG Health Monitor iniciando — intervalo: 60s
```

---

## Variáveis de ambiente

| Variável | Default | Descrição |
|---|---|---|
| `MONITOR_INTERVAL` | `60` | Intervalo entre coletas em segundos |
| `MEM_WARN_PERCENT` | `90` | Percentual de RAM para gerar WARNING no error.log |
| `LOGS_BASE` | `/logs` | Pasta base dos logs dentro do container |

---

## Estrutura de logs

Os logs são gravados no host no caminho mapeado pelo volume (`/home/lapig/applications/service/jupyterHub/logs`), com a seguinte estrutura:

```
logs/
├── jupyterhub/
│   ├── health.log      # Linhas [I] do Hub: spawns, logins, rotas
│   └── error.log       # Linhas [W][E][C] do Hub: warnings e erros
└── users/
    ├── aurilio/
    │   ├── health.log  # Saúde periódica: CPU, RAM, uptime, PIDs
    │   └── error.log   # OOM, crashes, alta memória
    ├── tiago/
    │   ├── health.log
    │   └── error.log
    └── ...             # Criado automaticamente para cada usuário
```

Cada arquivo de log é **append-only** — nunca sobrescrito, sempre acumulado. Implemente rotação externa (ex: `logrotate`) se necessário para ambientes de longa duração.

---

## Exemplos de log

### `logs/users/<username>/health.log`

Registrado a cada minuto para containers ativos:

```
2026-09-02 19:30:00 | aurilio | RUNNING | CPU: 2.3% | RAM: 1.20G/2.00G (60.0%) | UPTIME: 2h 5m 10s | PIDS: 12
2026-09-02 19:31:00 | aurilio | RUNNING | CPU: 1.8% | RAM: 1.21G/2.00G (60.5%) | UPTIME: 2h 6m 10s | PIDS: 12
```

### `logs/users/<username>/error.log` — OOM Kill (CRITICAL)

Gerado quando o kernel encerra o container por falta de memória (exit code 137):

```
2026-09-02 20:00:00 | SEVERITY: CRITICAL | USER: aurilio | CONTAINER: jupyter-aurilio
  EVENT    : OOM_KILLED
  REASON   : Container excedeu o limite de memória (mem_limit: 2.00G)
  MEM_USAGE: 2.00G / 2.00G (100.0%)
  CPU_USAGE: 45.2%
  UPTIME   : 3h 22m 0s
  PID_COUNT: 47
  EXIT_CODE: 137
  RESTARTED: False
  ACTION   : Container morto pelo kernel — OOM Killer ativado
  ----------------------------------------
```

### `logs/users/<username>/error.log` — Alta memória (WARNING)

Gerado quando o container ultrapassa o threshold de `MEM_WARN_PERCENT`:

```
2026-09-02 19:50:00 | SEVERITY: WARNING | USER: aurilio | CONTAINER: jupyter-aurilio
  EVENT    : HIGH_MEMORY
  MEM_USAGE: 1.85G / 2.00G (92.5%)
  CPU_USAGE: 78.1%
  THRESHOLD: 90.0% do limite
  UPTIME   : 3h 12m 0s
  ACTION   : Aviso — container próximo do limite de memória
  ----------------------------------------
```

### `logs/users/<username>/error.log` — Exit code anormal (ERROR)

Gerado quando o container encerra com código diferente de 0 e sem ser OOM:

```
2026-09-02 21:00:00 | SEVERITY: ERROR | USER: tiago | CONTAINER: jupyter-tiago
  EVENT    : CONTAINER_EXITED
  EXIT_CODE: 1
  REASON   : Saída anormal (código diferente de 0)
  MEM_USAGE: 800M / 2.00G (40.0%)
  CPU_USAGE: 0.0%
  UPTIME   : 1h 5m 0s
  LAST_LOGS:
    Traceback (most recent call last):
    ...
  ----------------------------------------
```