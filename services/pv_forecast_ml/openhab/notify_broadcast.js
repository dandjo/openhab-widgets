// A push notification to every device of openHAB Cloud, with the text its caller passes. Create it in openHAB as a
// script (Settings, Scripts, a new script in JavaScript, ECMAScript 2021+) with the UID notify_broadcast. A service
// outside openHAB runs it with POST /rest/rules/notify_broadcast/runnow and the body {"message": "..."}; openHAB hands
// the body's keys to the script as variables. pv_forecast_ml does so when its nightly check discards a new model.
if (typeof message === 'undefined' || String(message).trim() === '') {
  console.warn('notification without a text, nothing sent');
} else {
  actions.NotificationAction.sendBroadcastNotification(String(message));
  console.info(`notification sent: ${message}`);
}
