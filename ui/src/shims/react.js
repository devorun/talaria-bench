// Dashboard build only: React is never bundled; the dashboard hands plugins its own instance.
const R = window.__HERMES_PLUGIN_SDK__.React
export default R
export const {
  Fragment, createElement, useState, useEffect, useRef, useMemo, useCallback, useLayoutEffect,
  useContext, createContext, memo,
} = R
