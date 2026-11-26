/// <reference types="svelte" />
/// <reference types="vite/client" />

declare module '*.svelte' {
  const component: import('svelte').Component<any>;
  export default component;
}
