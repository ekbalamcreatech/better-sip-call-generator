// Escape untrusted text for use in HTML text AND attribute contexts.
// Everything that comes from the server, a SIP peer, a file name or a user
// must go through this before being placed in innerHTML.
function escapeHtml(str) {
  return (str == null ? '' : String(str))
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/`/g, '&#96;');
}
