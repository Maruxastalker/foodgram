// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';


if (typeof global.clearImmediate === 'undefined') {
  global.clearImmediate = function(id) {
    clearTimeout(id);
  };
}

if (typeof global.setImmediate === 'undefined') {
  global.setImmediate = function(fn) {
    return setTimeout(fn, 0);
  };
}