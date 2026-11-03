"""Working-memory prompts exposed as H candidate parameters."""




def update_prompt(instructions, previous, evidence, tokens):
    return (instructions + '\nMemory budget: ' + str(tokens) + ' estimated tokens.\n<previous>\n'
        + previous + '\n</previous>\n<evidence>\n' + evidence + '\n</evidence>')
