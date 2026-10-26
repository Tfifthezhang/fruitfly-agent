// Static source fixture. No installation, network access or execution is needed.
export function normalizeQuery(value) {
  return String(value).trim().toLowerCase();
}

export function searchNotes(notes, query) {
  const normalized = normalizeQuery(query);
  return notes.filter(note => normalizeQuery(note.title).includes(normalized));
}
