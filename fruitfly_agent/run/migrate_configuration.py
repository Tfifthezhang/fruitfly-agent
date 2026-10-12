"""Supported Run entry point; implementation belongs to its owning module."""
from .configuration.migration import migrate_configuration, main

if __name__ == "__main__":
    main()
