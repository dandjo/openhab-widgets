// A push notification to every device of openHAB Cloud (user, 2026-10-20), with the text its caller passes: run with
// POST /rest/rules/notify_broadcast/runnow and the body {"message": "..."}, for services outside openHAB that cannot
// call openHAB's actions, such as pv_forecast_ml when its nightly check discards a new model.
if (typeof message === 'undefined' || String(message).trim() === '') {
  console.warn('Benachrichtigung ohne Text aufgerufen, nichts gesendet');
} else {
  actions.NotificationAction.sendBroadcastNotification(String(message));
  console.info(`Benachrichtigung gesendet: ${message}`);
}
