// Dashboard build only: the automatic JSX runtime on top of the dashboard's React instance.
// createElement accepts children inside props, so jsx(type, props, key) maps onto it directly.
const R = window.__HERMES_PLUGIN_SDK__.React
export const Fragment = R.Fragment
export function jsx(type, props, key) {
  return R.createElement(type, key === undefined ? props : { ...props, key })
}
export const jsxs = jsx
