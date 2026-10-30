"""Extension inspection and idle reload through public Application operations."""
from fruitfly_agent.interactive.contracts.commands import CommandResult


def bind_extension_commands(registry, application, factory):
    active = [factory]
    factory.extensions.bind_commands(registry)

    def describe(command):
        return CommandResult(text='\n'.join(
            row['source'] + ' · ' + row['implementation'] for row in active[0].extensions.identities))

    async def reload(command):
        if application.state.value != 'idle':
            raise RuntimeError('finish active work before reloading extensions')
        replacement = active[0].replacement_extensions()
        commit = registry.prepare_group('extensions', replacement.extensions.command_entries())
        await application.replace_factory(replacement)
        active[0] = replacement
        commit()
        return CommandResult(text='Extensions reloaded; conversation retained.')

    registry.register('extensions', describe, summary='Inspect loaded Python extensions')
    registry.register('reload', reload, summary='Reload extensions while idle')
