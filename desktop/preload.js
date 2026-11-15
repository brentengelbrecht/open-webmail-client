'use strict';
// The only bridge the password window gets: send the password, or ask for a reset.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('masterPrompt', {
  submit: (password) => ipcRenderer.send('prompt:submit', password),
  reset: () => ipcRenderer.send('prompt:reset'),
});
