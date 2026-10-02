## Feature / Epic

**Driving Licence Reminder**

Help drivers in Estonia remain aware of driving-licence and medical-certificate deadlines, so they can renew in time and avoid their driving status becoming invalid.

---

## Parent User Story

**Title:** Receive timely driving licence renewal reminders

As a driver in Estonia,
I want to receive reminders before my driving licence or required medical certificate expires,
so that I can complete renewal actions on time and maintain my right to drive.

---

## Child Implementation Stories

### US-01: Log in

As a user,
I want to log in securely,
so that I can access only my own driving information and reminder settings.

**Acceptance Criteria**
- Given I am not logged in, when I enter valid authentication details, then I am logged in and taken to my profile.
- Given I enter invalid authentication details, when I try to log in, then I see an understandable error message.
- Given I am logged in, then I can access driving information and reminder settings.

---

### US-02: Log out

As a logged-in user,
I want to log out,
so that I can protect my personal driving information on a shared device.

**Acceptance Criteria**
- Given I am logged in, when I select **Log out**, then my session ends.
- Given I have logged out, when I try to access protected information, then I am asked to log in again.

---

### US-03: View profile and driving status

As a driver,
I want to view my profile and current driving status,
so that I know whether I am currently allowed to drive.

**Acceptance Criteria**
- Given I am logged in, when I open my profile, then I can see my current driving status.
- The driving status is clearly shown as `Valid`, `At risk`, or `Invalid`.
- Given my status is `At risk` or `Invalid`, then I can see an explanation of the reason.

---

### US-04: View licence and medical-certificate details

As a driver,
I want to view my driving licence and medical certificate information,
so that I understand which document or requirement needs attention.

**Acceptance Criteria**
- Given I open my driving information, then I can view my driving licence details, including licence categories and expiry date.
- Given medical-certificate data applies to me, then I can view its status and expiry date.
- Given multiple deadlines exist, then the earliest relevant deadline is displayed as my next expiry deadline.

---

### US-05: Refresh driving data from X-Road

As a driver,
I want to refresh my driving information from X-Road,
so that I can make decisions using the latest available data.

**Acceptance Criteria**
- Given I am on the driving information page, when I select **Refresh**, then the system requests current information through the approved X-Road integration.
- Given the refresh succeeds, then the latest driving status, document details, and expiry information are displayed.
- Given the refresh fails, then I see a clear error message, the last available information remains visible, and I can see when it was last updated.
- Given I view driving information, then I can see the date and time of its latest successful update.

---

### US-06: View renewal guidance

As a driver whose document or certificate is expiring,
I want to view renewal instructions,
so that I know what actions I need to take before the deadline.

**Acceptance Criteria**
- Given my driving licence or medical certificate is approaching expiry, expired, or causes my status to be at risk, when I select **Renewal instructions**, then I see relevant Estonia-specific guidance.
- The guidance clearly identifies whether I need to renew my driving licence, obtain or renew a medical certificate, or complete both actions.
- The guidance provides a clear description of the recommended next step.
- The guidance includes a route to the official renewal service.

---

### US-07: Open the official renewal service

As a driver,
I want to open the official renewal service from the app,
so that I can begin the renewal process without searching for the service myself.

**Acceptance Criteria**
- Given I am viewing renewal instructions, when I select **Open official renewal service**, then the application opens the official Estonian Transport Administration e-service in my device's default web browser.
- Before opening the external service, the application clearly informs me that I will continue on an official external website.
- The application opens the relevant driving-licence renewal or exchange page where available.
- Given the external service cannot be opened, then I see a clear error message and the official service address.

---

### US-08: Enable reminders

As a driver,
I want to enable expiry reminders,
so that I receive notice before my licence or medical certificate expires.

**Acceptance Criteria**
- Given reminders are disabled, when I select **Enable reminders**, then the system enables reminders for my next relevant expiry deadline.
- Given I enable reminders, then the system clearly confirms that reminders are active.
- Given notification permission is required by my device, then the system asks for my permission before sending notifications.
- Given notification permission is denied, then the system explains that reminders cannot be delivered until permission is enabled.

---

### US-09: Change reminder settings

As a driver,
I want to change my reminder settings,
so that I can control when I receive expiry reminders.

**Acceptance Criteria**
- Given reminders are enabled, when I open reminder settings, then I can view my current reminder configuration.
- I can select which available reminder intervals I want to use.
- When I save my changes, then future reminders follow the updated settings.
- The system confirms that my reminder settings have been saved.

---

### US-10: View previous notifications

As a driver,
I want to view previous reminder notifications,
so that I can see which expiry reminders have already been sent to me.

**Acceptance Criteria**
- Given I open **Previous notifications**, then I can see recent notifications with the newest first.
- Each notification shows the date and time it was sent.
- Each notification identifies whether it concerned my driving licence or medical certificate.
- Each notification shows the relevant expiry date.
- The system displays a limited number of recent notifications to keep the history clear and manageable.
