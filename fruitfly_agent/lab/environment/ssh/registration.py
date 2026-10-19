"""Catalog registration of the SSH backend and its non-secret inputs."""
from dataclasses import replace
from pathlib import Path

from fruitfly_agent.core.mechanisms import MechanismContribution, MechanismDescriptor, MechanismEffects, ParameterDescriptor
from fruitfly_agent.lab.catalog.models import MechanismDefinition, MechanismSetup, SetupCredential
from fruitfly_agent.lab.improvement.contracts.versions import EXPERIMENT_BLOCKERS_COMPONENT
from .config import SshConfig
from .environment import SshEnv


def definition():
    return MechanismDefinition(
        MechanismDescriptor('ssh-env', 'SSH server',
            'Read and write server files and run Bash commands over verified SSH.',
            contributions=(MechanismContribution('capability', 'environment'),),
            parameters=(
                ParameterDescriptor('host', 'string', 'Server address', 'Hostname or IP address; no account or port.', ''),
                ParameterDescriptor('port', 'integer', 'SSH port', 'Server SSH TCP port.', 22, minimum=1, maximum=65535),
                ParameterDescriptor('cwd', 'string', 'Remote directory', 'Existing absolute POSIX working directory on the server.', '/srv/workspace'),
                ParameterDescriptor('username_env', 'string', 'Account variable', 'Secret environment variable name, never the account value.', 'FRUITFLY_SSH_USERNAME'),
                ParameterDescriptor('password_env', 'string', 'Password variable', 'Secret environment variable name, never the password value.', 'FRUITFLY_SSH_PASSWORD'),
                ParameterDescriptor('known_hosts', 'string', 'Known hosts file', 'Local verified OpenSSH known_hosts file; relative to the local workspace.', '~/.ssh/known_hosts'),
                ParameterDescriptor('connect_timeout_seconds', 'number', 'Connection deadline', 'Seconds for each SSH connection phase.', 15, minimum=.1, maximum=300),
                ParameterDescriptor('operation_timeout_seconds', 'number', 'I/O deadline', 'Seconds for SFTP and SSH channel operations.', 30, minimum=.1, maximum=300),
            ),
            exclusive_group='environment', install_order=10,
            conflicts=frozenset({'ipython-tool', 'memory-files'}),
            effects=MechanismEffects(uses_network=True, writes_files=True,
                cost_notice='Selected file and Bash tools operate on the configured server with the remote account permissions.')),
        install, implementation_id='ssh-env-v1', provides=frozenset({'execution-env'}),
        implementation_path='fruitfly_agent/lab/environment/ssh/environment.py',
        documentation_path='fruitfly_agent/lab/environment/ssh/README.md',
        input_parameters=('host', 'port', 'cwd', 'username_env', 'password_env', 'known_hosts'),
        validate_parameters=validate,
        setup=MechanismSetup(
            fields=('host', 'port', 'cwd', 'known_hosts'),
            required_fields=('host', 'cwd', 'known_hosts'),
            credentials=(
                SetupCredential('username_env', 'Account', 'Enter the SSH login account. Hidden input is excluded from history.'),
                SetupCredential('password_env', 'Password', 'Enter the SSH login password. Hidden input is excluded from history.'),
            ),
            guidance='The server needs SFTP, python3, /bin/bash and an existing working directory. '
                'Verify its host-key fingerprint through a trusted source using your SSH client first; '
                'unknown or changed host keys are rejected. Setup makes no network requests.',
        ),
    )


def validate(parameters):
    # Reject literal credential fields without reflecting their values in errors.
    if any(key in parameters for key in ('username', 'password', 'account', 'api_key')):
        raise ValueError('SSH credentials belong in the secret environment; use username_env and password_env')
    known = SshConfig.__dataclass_fields__
    SshConfig(**{key: value for key, value in parameters.items() if key in known})


def install(state, context, parameters):
    config = SshConfig(**parameters)
    secrets = context.secret_resolver
    username = secrets(config.username_env) if secrets is not None else None
    password = secrets(config.password_env) if secrets is not None else None
    if not username or not password:
        raise ValueError('SSH account or password is missing from the host secret environment. Open Configure → Environment → SSH server → Set up… '
                         'or set the configured secret variables in .fruitfly/secrets.env')
    # Resolve only the local host-key path here; remote paths never use resolve().
    known_hosts = Path(config.known_hosts).expanduser()
    if not known_hosts.is_absolute():
        known_hosts = context.workspace / known_hosts
    backend = context.own(SshEnv(replace(config, known_hosts=str(known_hosts)), username=username, password=password))
    prompt = ('Execution environment: remote SSH server ' + config.host + ':' + str(config.port) +
              '. File and Bash tools use remote directory ' + config.cwd +
              '. Sessions, skills and context sources remain on the local host; files are not synchronized.')
    state = replace(state, config=replace(state.config, env=backend,
        system_prompt=(state.config.system_prompt + '\n\n' + prompt).strip()))
    return state.with_component('ssh-environment', backend).with_component(EXPERIMENT_BLOCKERS_COMPONENT,
        (*state.components.get(EXPERIMENT_BLOCKERS_COMPONENT, ()),
         'Remote SSH workspace has no isolated frozen task snapshot'))
