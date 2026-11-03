"""Editable guidance; source references and output structure are code-owned."""

SECTIONS = ('Request and constraints', 'Work and decisions', 'Technical details',
            'Files and changes', 'Errors and uncertainty', 'Pending work and next action')




def summary_prompt(instructions, material, target_tokens):
    headings = '\n'.join('## ' + name for name in SECTIONS)
    return (instructions + '\nReturn text only, with each of these headings exactly once and in order:\n'
        + headings + '\nAim for at most ' + str(target_tokens) + ' estimated tokens.\n'
        'Use only the evidence supplied below.\n<evidence>\n' + material + '\n</evidence>')
