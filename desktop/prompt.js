'use strict';
const params = new URLSearchParams(location.search);
const creating = params.get('mode') === 'create';
const min = Number(params.get('min')) || 8;
const $ = (id) => document.getElementById(id);

$('intro').textContent = creating
  ? `Choose a master password (at least ${min} characters). You will enter it on the sign-in screen each time you open the app, and it protects your saved mail accounts. There is no way to recover it.`
  : 'Enter your master password to open your saved accounts.';
$('notice').textContent = params.get('notice') || '';
$('password').placeholder = creating ? 'New master password' : 'Master password';
$('password').autocomplete = creating ? 'new-password' : 'current-password';
$('repeat').hidden = !creating;
$('repeat').required = creating;
$('reset').hidden = creating;
$('go').textContent = creating ? 'Create password' : 'Continue';

$('form').addEventListener('submit', (event) => {
  event.preventDefault();
  const password = $('password').value;
  if (creating && password.length < min) { $('error').textContent = `Use at least ${min} characters.`; return; }
  if (creating && password !== $('repeat').value) { $('error').textContent = 'The two passwords do not match.'; return; }
  $('error').textContent = '';
  $('go').disabled = true;
  window.masterPrompt.submit(password);
});
$('reset').addEventListener('click', () => window.masterPrompt.reset());
