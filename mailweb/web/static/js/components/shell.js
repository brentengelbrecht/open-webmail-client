// Switches between the login screen and the mail layout, and mounts the feature components.
import { h, render } from '../util/dom.js';
import { clampPanes } from '../util/panes.js';
import { pageSpinner } from '../util/spinner.js';
import { mountLogin } from './login.js';
import { mountGutter } from './gutter.js';
import { createAccountDialog } from './accountDialog.js';
import { createEditAccountDialog } from './editAccountDialog.js';
import { createSplitters } from './splitters.js';
import { mountHeader } from './header.js';
import { mountSidebar } from './sidebar.js';
import { mountMessageList } from './messageList.js';
import { mountReader } from './reader.js';

export function mountShell(root, store, actions) {
  let scope = null;          // subscriptions of the currently mounted mail layout
  let stopResize = null;

  store.select((s) => [s.authenticated, s.booting], ([authenticated, booting]) => {
    scope?.dispose();
    stopResize?.();
    scope = stopResize = null;

    if (booting) return render(root, pageSpinner());

    if (!authenticated) {
      document.body.classList.remove('sidebar-open', 'has-message');
      return mountLogin(root, { notice: store.get().loginNotice, onSubmit: (password) => actions.login(password) });
    }

    scope = store.scoped();
    const parts = ['nav', 'header', 'aside', 'section', 'main'].map((tag, i) =>
      h(tag, { class: ['gutter', 'topbar', 'sidebar', 'list', 'reader'][i] }));
    const [gutter, header, sidebar, list, reader] = parts;
    const dialog = createAccountDialog({ onAdd: (details) => actions.addAccount(details) });
    const splitters = createSplitters({ sidebar, list }, scope, actions);
    const editDialog = createEditAccountDialog({ onSave: (id, changes) => actions.updateAccount(id, changes) });
    const layout = h('div', { class: 'layout' }, parts, splitters.elements, dialog.element, editDialog.element);
    render(root, layout);

    const sidebarBox = h('div', { class: 'sidebar-inner' });
    sidebar.append(sidebarBox);
    const onAddAccount = () => dialog.open();
    mountGutter(gutter, scope, actions, { onAddAccount });
    mountHeader(header, scope, actions);
    mountSidebar(sidebarBox, scope, actions, { onEditAccount: (account) => editDialog.open(account) });
    mountMessageList(list, scope, actions, { onAddAccount });
    mountReader(reader, scope, actions);

    // Pane sizes -> CSS variables, re-clamped whenever the window changes size.
    const applyPanes = () => {
      const p = clampPanes(store.get().panes, { width: window.innerWidth, height: window.innerHeight });
      layout.style.setProperty('--sidebar-w', `${p.sidebar}px`);
      layout.style.setProperty('--list-w', `${p.listWidth}px`);
      layout.style.setProperty('--list-h', `${p.listHeight}px`);
    };
    scope.select((s) => s.panes, applyPanes);
    scope.select((s) => s.layout, splitters.orient);
    window.addEventListener('resize', applyPanes);
    stopResize = () => window.removeEventListener('resize', applyPanes);
  });

  store.select((s) => Boolean(s.route.uid), (open) => document.body.classList.toggle('has-message', open));
  store.select((s) => s.layout, (layout) => { document.body.dataset.layout = layout; });

  document.addEventListener('keydown', (event) => {
    const { layout, route, authenticated } = store.get();
    if (event.key === 'Escape' && authenticated && layout === 'full' && route.uid && !document.querySelector('dialog[open]')) {
      actions.closeMessage();
    }
  });

  // Collapse/expand the folder list. The animation class is on only briefly, so dragging a splitter never lags.
  let animationTimer = null;
  let firstRun = true;
  store.select((s) => s.sidebarCollapsed, (collapsed) => {
    const body = document.body;
    if (!firstRun) {
      body.classList.add('sidebar-animating');
      clearTimeout(animationTimer);
      animationTimer = setTimeout(() => body.classList.remove('sidebar-animating'), 350);
    }
    firstRun = false;
    body.classList.toggle('sidebar-collapsed', collapsed);
  });
}
