ObjC.import('Foundation');

function run() {
  const lines = [];

  try {
    const safari = Application('Safari');
    safari.activate();
    sleep(0.5);

    if (safari.documents.length > 0) {
      try {
        safari.doJavaScript('document.title', { in: safari.documents[0] });
        lines.push('Safari automation: OK');
      } catch (error) {
        lines.push(`Safari automation: needs Safari Develop > Allow JavaScript from Apple Events (${error.message || String(error)})`);
      }
    } else {
      lines.push('Safari automation: open any Safari page, then run this again');
    }
  } catch (error) {
    lines.push(`Safari automation: blocked (${error.message || String(error)})`);
  }

  try {
    const systemEvents = Application('System Events');
    systemEvents.keyCode(53);
    lines.push('Accessibility keystrokes: OK');
  } catch (error) {
    lines.push(`Accessibility keystrokes: needs approval in System Settings > Privacy & Security > Accessibility (${error.message || String(error)})`);
  }

  return lines.join('\n');
}

function sleep(seconds) {
  $.NSThread.sleepForTimeInterval(seconds);
}
