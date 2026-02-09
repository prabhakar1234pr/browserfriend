"""Send a test email to verify SMTP configuration."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from browserfriend.email.sender import send_dashboard_email

html = """
<html>
<body style="font-family: Arial, sans-serif; padding: 30px; background: #f4f7fa;">
  <div style="max-width: 500px; margin: 0 auto; background: white; border-radius: 12px; padding: 30px; box-shadow: 0 2px 12px rgba(0,0,0,0.08);">
    <h1 style="color: #1a73e8; text-align: center;">BrowserFriend</h1>
    <p style="text-align: center; color: #5f6368;">Test Email</p>
    <hr style="border: 1px solid #e8eaed;">
    <p style="color: #202124;">This is a test email from BrowserFriend to verify that email delivery is working correctly.</p>
    <p style="color: #4CAF50; font-weight: bold; text-align: center;">Email delivery is configured and working!</p>
  </div>
</body>
</html>
"""

print("Sending test email to prabhakarelavala1@gmail.com ...")
result = send_dashboard_email("prabhakarelavala1@gmail.com", html)

if result:
    print("SUCCESS - Email sent! Check your inbox.")
else:
    print("FAILED - Email could not be sent. See error above.")

sys.exit(0 if result else 1)
