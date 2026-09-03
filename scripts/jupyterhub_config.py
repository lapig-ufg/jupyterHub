import os
import dockerspawner
from oauthenticator.generic import GenericOAuthenticator

# --- CONFIGURAÇÃO PADRÃO DO CONTAINER DE USUÁRIO ---
docker_default = {
    "image": os.environ.get('lapig/jupterlab:v3.0.7'),
    "mem_limit": os.environ.get('4G'),
    "cpu_limit": int(os.environ.get('DOCKER_CPU_LIMIT', 1)),
    "network_name": os.environ.get('DOCKER_NETWORK_NAME', 'web_lapig_sci2'),
    "volumes": {
        "/home/lapig/applications/storage/jupyterhub/users/{username}": "/work",
        "/home/lapig/applications/storage/jupyterhub/users/{username}/.ssh": "/home/jovyan/.ssh",
        "/home/lapig/applications/storage/jupyterhub/shared": "/work/shared"
    }
}

NOTEBOOK_UID = int(os.environ.get('NOTEBOOK_UID', 1000))
NOTEBOOK_GID = int(os.environ.get('NOTEBOOK_GID', 100))
STORAGE_BASE = "/home/lapig/applications/storage/jupyterhub/users"


# --- SPAWNER CUSTOMIZADO ---
# Ajusta permissões DEPOIS que o container está de pé, usando a
# biblioteca docker (que o DockerSpawner já usa internamente), em vez
# do CLI 'docker' — que não está instalado na imagem do Hub.
class CustomDockerSpawner(dockerspawner.DockerSpawner):
    async def start(self):
        ip_port = await super().start()

        username = self.user.name
        container_name = f"jupyter-{username}"

        try:
            # self.docker() roda métodos do cliente docker-py de forma
            # thread-safe. Cria um exec, depois inicia ele.
            exec_id = await self.docker(
                "exec_create",
                container=container_name,
                cmd=["chown", "-R", f"{NOTEBOOK_UID}:{NOTEBOOK_GID}", "/work", "/home/jovyan/.ssh"],
                user="root",
            )
            await self.docker("exec_start", exec_id=exec_id["Id"], detach=True)
            self.log.info(f"[chown] Permissões ajustadas para {username}")
        except Exception as e:
            self.log.error(f"[chown] ERRO ao ajustar permissões de {username}: {e}")

        return ip_port

async def user_docker_config(spawner):
    auth_state = await spawner.user.get_auth_state() or {}
    user_info = auth_state.get('oauth_user', {})

    username = spawner.user.name

    spawner.notebook_dir = "/work"
    spawner.image = user_info.get('image_container', docker_default['image'])
    spawner.network_name = docker_default['network_name']
    spawner.mem_limit = user_info.get('mem_limit', docker_default['mem_limit'])

    cpu_raw = user_info.get('cpu_limit', docker_default['cpu_limit'])
    spawner.cpu_limit = int(cpu_raw)

    spawner.volumes = docker_default['volumes']

    user_dir = f"{STORAGE_BASE}/{username}"
    ssh_dir = f"{user_dir}/.ssh"

    os.makedirs(user_dir, exist_ok=True)
    os.makedirs(ssh_dir, exist_ok=True)
    print(f"[pre_spawn_hook] Diretórios garantidos: {user_dir}", flush=True)


# --- REDE E SSL DO JUPYTERHUB ---
c.JupyterHub.bind_url = os.environ.get('JUPYTERHUB_BIND_URL', 'http://0.0.0.0:443')
c.JupyterHub.hub_ip = '0.0.0.0'
c.JupyterHub.hub_connect_ip = os.environ.get('HUB_CONNECT_IP', 'jupyterhub')


# --- AUTENTICAÇÃO KEYCLOAK (OAUTHENTICATOR) ---
c.JupyterHub.authenticator_class = GenericOAuthenticator

c.GenericOAuthenticator.client_id = os.environ.get('OAUTH_CLIENT_ID')
c.GenericOAuthenticator.client_secret = os.environ.get('OAUTH_CLIENT_SECRET')
c.GenericOAuthenticator.authorize_url = os.environ.get('OAUTH_AUTHORIZE_URL')
c.GenericOAuthenticator.token_url = os.environ.get('OAUTH_TOKEN_URL')
c.GenericOAuthenticator.oauth_callback_url = os.environ.get('OAUTH_CALLBACK_URL')

c.GenericOAuthenticator.userdata_from_id_token = True
c.GenericOAuthenticator.username_claim = 'preferred_username'
c.GenericOAuthenticator.scope = ['openid', 'profile', 'email', 'groups']
c.GenericOAuthenticator.auth_state_groups_key = 'oauth_user.groups'
c.GenericOAuthenticator.manage_groups = True
c.GenericOAuthenticator.allowed_groups = {'jupyterhub2_users', '/jupyterhub2_users'}

c.GenericOAuthenticator.admin_groups = {'/lapig-admin'}
c.GenericOAuthenticator.enable_auth_state = True


# --- SPAWNER (DOCKER) ---
c.JupyterHub.spawner_class = CustomDockerSpawner
c.Spawner.pre_spawn_hook = user_docker_config

c.DockerSpawner.network_name = docker_default['network_name']
c.DockerSpawner.use_internal_ip = True
c.DockerSpawner.pull_policy = 'ifnotpresent'
c.DockerSpawner.remove = False
c.DockerSpawner.debug = True

c.Spawner.start_timeout = int(os.environ.get('SPAWNER_START_TIMEOUT', 300))
c.Spawner.http_timeout = int(os.environ.get('SPAWNER_HTTP_TIMEOUT', 300))