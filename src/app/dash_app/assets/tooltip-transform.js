/*
 * tooltip-transform.js
 *
 * Dash clientside transform functions for tooltip display.
 * Registered in window.dccFunctions — referenced by tooltip.transform
 * on dcc.Slider and dcc.RangeSlider components.
 *
 * Namespace: window.dccFunctions
 *
 * Dependencies:
 *   window.UI_DATE_FORMAT      — strftime format string for date-only display
 *                                (set by layout.py clientside callback)
 *   window.UI_DATETIME_FORMAT  — strftime format string for datetime display
 *                                (set by layout.py clientside callback)
 *
 * Functions:
 *   strftime(fmt, date) — lightweight strftime implementation for Date objects.
 *                         Supports: %Y %y %m %b %B %d %H %I %M %S %p %%
 *
 *   epochDayToDate(value) — converts an integer days-since-epoch to
 *                           a formatted date string using window.UI_DATE_FORMAT.
 *                           Used by the graph page time-based RangeSliders
 *                           whose values are days since Unix epoch (UTC).
 */

window.dccFunctions = window.dccFunctions || {};

/**
 * Lightweight strftime implementation.
 * Supported specifiers: %Y %y %m %b %B %d %H %I %M %S %p %%
 *
 * @param {string} fmt — strftime format string (e.g. "%b %d, %Y")
 * @param {Date} date  — JavaScript Date object
 * @returns {string} formatted date string
 */
window.dccFunctions.strftime = function (fmt, date) {
    var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    var monthsFull = ['January', 'February', 'March', 'April', 'May', 'June',
                      'July', 'August', 'September', 'October', 'November', 'December'];
    var pad = function (n) { return (n < 10 ? '0' : '') + n; };

    return fmt.replace(/%[YymbBdHI%MpS]/g, function (match) {
        switch (match) {
            case '%Y': return String(date.getUTCFullYear());
            case '%y': return String(date.getUTCFullYear()).slice(-2);
            case '%m': return pad(date.getUTCMonth() + 1);
            case '%b': return months[date.getUTCMonth()];
            case '%B': return monthsFull[date.getUTCMonth()];
            case '%d': return pad(date.getUTCDate());
            case '%H': return pad(date.getUTCHours());
            case '%I': var h = date.getUTCHours() % 12 || 12; return pad(h);
            case '%M': return pad(date.getUTCMinutes());
            case '%S': return pad(date.getUTCSeconds());
            case '%p': return date.getUTCHours() < 12 ? 'AM' : 'PM';
            case '%%': return '%';
            default:  return match;
        }
    });
};

window.dccFunctions.epochDayToDate = function (value) {
    var date = new Date(Date.UTC(1970, 0, 1 + value));
    var fmt = window.UI_DATE_FORMAT || '%b %d, %Y';
    return window.dccFunctions.strftime(fmt, date);
};