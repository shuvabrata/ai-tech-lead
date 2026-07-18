/*
 * tooltip-transform.js
 *
 * Dash clientside transform functions for tooltip display.
 * Registered in window.dccFunctions — referenced by tooltip.transform
 * on dcc.Slider and dcc.RangeSlider components.
 *
 * Namespace: window.dccFunctions
 *
 * Functions:
 *   epochDayToDate(value) — converts an integer days-since-epoch to
 *                           a human-readable "dd-mmm-yy" format (e.g. "6-Jun-26").
 *                           Used by the graph page time-based RangeSliders
 *                           whose values are days since Unix epoch (UTC).
 */

window.dccFunctions = window.dccFunctions || {};

window.dccFunctions.epochDayToDate = function (value) {
    var date = new Date(Date.UTC(1970, 0, 1 + value));
    var day = date.getUTCDate();
    var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    var month = months[date.getUTCMonth()];
    var year = date.getUTCFullYear().toString().slice(-2);
    return day + '-' + month + '-' + year;
};