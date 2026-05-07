import '@testing-library/jest-dom'
import React from 'react'
globalThis.React = React

// jsdom doesn't implement scrollIntoView
Element.prototype.scrollIntoView = () => {}
