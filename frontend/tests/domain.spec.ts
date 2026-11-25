import { test, expect } from "@playwright/test";
import { date, reminderDate, ApiError, errorText } from "../src/api";
test("calendar deadline labels preserve calendar dates through year and leap boundaries", () => {
  expect(date(null)).toBe("Unavailable");
  expect(reminderDate(null, 30)).toBeNull();
  expect(reminderDate("2028-03-07", 7)).toBe("29 Feb 2028");
  expect(reminderDate("2027-01-01", 30)).toBe("2 Dec 2026");
});
test("failure feedback keeps the application code and hides unexpected exception text", () => {
  expect(errorText(new ApiError(401, "AUTH_REQUIRED", "Log in again."))).toBe(
    "Log in again. (AUTH_REQUIRED)",
  );
  expect(errorText(new Error("private diagnostic"))).not.toContain(
    "private diagnostic",
  );
});
