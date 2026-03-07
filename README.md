# Sport Court Booking Automation

This repository contains an automated system for booking tennis courts at Telford Park Tennis Club. The system uses GitHub Actions to automatically book courts every Saturday for two weeks in advance.

## Schedule

The system runs automatically at the following times:

### Saturday Bookings
- **Cron**: Two schedules fire ~10 minutes before midnight UK time (Friday night): `22:50` and `23:50` UTC so it works in both GMT and BST.
- **Execution**: The script waits until exactly midnight UK time, then books as fast as possible.
- **Time slots**: Tries primary block 11:00 + 12:00 first; if 11:00 is unavailable, falls back to 12:00 + 13:00. User1 books the first hour, User2 the second (same court preferred).

## System Design

### Scheduling and Validation
The system uses:

1. **Dual cron schedules** (Friday 22:50 and 23:50 UTC) so one of them is ~10 minutes before midnight UK in both GMT and BST.
2. **Workflow timing check**: Allows Friday 22:00–23:59 or Saturday 00:00–05:59 UK time.
3. **Python wait-until-midnight**: Script waits until exactly midnight UK time (sub-second precision), then runs the booking. If midnight is more than 20 minutes away, it exits (wrong cron for current period).
4. **Pre-warm**: User1 is logged in before midnight so the actual booking runs immediately at 00:00.

Manual runs (workflow_dispatch) can use **Test mode** to skip the midnight wait and run immediately.

## Setup

### 1. Create a GitHub Repository
1. Go to [github.com](https://github.com) and sign in (or create an account if you don't have one)
2. Click the "+" icon in the top right corner
3. Select "New repository"
4. Name it something like "sport-court-booker"
5. Make it Public (to enable easier monitoring of GitHub Actions)
6. Click "Create repository"
7. Once created, upload all the files from this project to your new repository:
   - `court_booker.py`
   - `.github/workflows/court-booking.yml`
   - `README.md`

### 2. Configure Repository Secrets
1. In your new repository, click on "Settings" (top navigation bar)
2. In the left sidebar, click on "Secrets and variables"
3. Select "Actions"
4. Click the "New repository secret" button
5. Add each of these secrets one by one:

   #### LTA Credentials
   - `LTA_USERNAME`: First user's LTA username
   - `LTA_PASSWORD`: First user's LTA password
   - `LTA_USERNAME2`: Second user's LTA username
   - `LTA_PASSWORD2`: Second user's LTA password

   #### Email Notification Settings
   - `EMAIL_USERNAME`: Gmail address to send notifications from
   - `EMAIL_PASSWORD`: Gmail app password (not your regular password)
   - `NOTIFICATION_EMAILS`: Comma-separated list of email addresses to receive notifications (e.g., `user1@example.com,user2@example.com`)

   #### Setting up Gmail App Password:
   1. Go to your Google Account settings
   2. Navigate to Security
   3. Under "Signing in to Google," select 2-Step Verification
   4. At the bottom of the page, select "App passwords"
   5. Generate a new app password for "Mail"
   6. Use this generated password for the `EMAIL_PASSWORD` secret

### 3. Enable GitHub Actions
1. Go to the "Actions" tab in your repository
2. You should see the "Sport Court Booking" workflow
3. Click "Enable workflow"

The workflow will run at the scheduled time; the script waits until midnight UK then books immediately.

### 4. Pushing to GitHub from your machine

If you clone or work on the repo locally, you need to authenticate so `git push` works. Choose one method.

#### Option A: HTTPS with a Personal Access Token (simplest)

1. **Create a token on GitHub**
   - GitHub → **Settings** (your profile, top right) → **Developer settings** → **Personal access tokens** → **Tokens (classic)**
   - **Generate new token (classic)**. Name it e.g. `sport-court-booker`.
   - Enable scope: **repo** (full control).
   - Generate and **copy the token** (you won’t see it again).

2. **Use the token when pushing**
   - When you run `git push`, Git will ask for username and password.
   - **Username**: your GitHub username (e.g. `dan-r-mount`).
   - **Password**: paste the **token**, not your GitHub password.

3. **Save credentials on macOS (optional)**
   - So you don’t type the token every time:
   ```bash
   git config --global credential.helper osxkeychain
   ```
   - Next time you `git push` and enter the token, it will be stored in Keychain.

#### Option B: SSH key

1. **Create an SSH key** (if you don’t have one):
   ```bash
   ssh-keygen -t ed25519 -C "your_email@example.com" -f ~/.ssh/id_ed25519_github
   ```
   Press Enter for no passphrase, or set one.

2. **Add the public key to GitHub**
   - Copy the key: `cat ~/.ssh/id_ed25519_github.pub` (copy the full line).
   - GitHub → **Settings** → **SSH and GPG keys** → **New SSH key** → paste and save.

3. **Use SSH for this repo**
   ```bash
   cd /path/to/sport-court-booker
   git remote set-url origin git@github.com:dan-r-mount/sport-court-booker.git
   git push
   ```

4. **Optional: SSH config** so the right key is used:
   - Create or edit `~/.ssh/config`:
   ```
   Host github.com
     HostName github.com
     User git
     IdentityFile ~/.ssh/id_ed25519_github
   ```

## Email Notifications

After each run (successful or failed), the system will send an email containing:
- The day of booking (Saturday)
- A summary line indicating which hour was booked (11:00 or 12:00), or that no booking was made
- The date that the court has been booked for
- The court number that has been booked (if applicable)
- The actual LTA username that booked the court
- If any courts couldn't be booked, which courts were considered

## Manual trigger

1. Go to the **Actions** tab → **Sport Court Booking** → **Run workflow**.
2. **Test mode** (checkbox): when enabled, the script skips the midnight wait and runs the booking logic immediately. Use this to test without waiting for Saturday or midnight.
3. Without test mode, the workflow still checks that it’s Friday or Saturday UK time before running.

## Logs

The workflow logs will show:
- Login attempts
- Court availability
- Booking confirmations
- Any errors that occur during the process

## Court preferences and time blocks

- **Courts**: Preferred order is Court 5, 4, 3, 2, 1. For the second hour we prefer the same court as the first.
- **Time blocks**: Primary block is 11:00 (User1) + 12:00 (User2). If 11:00 is unavailable, we try 12:00 (User1) + 13:00 (User2).
- **Partial bookings**: If User1 gets a slot but User2 cannot get the next hour, we keep User1’s booking and report it.

## Troubleshooting

If the workflow fails:
1. Check the workflow logs in the Actions tab
2. Verify that your LTA credentials are correct
3. Ensure the repository has the necessary permissions to run GitHub Actions
4. Check your email settings if you're not receiving notifications

### Common Email Issues:
- Make sure you're using an App Password, not your regular Gmail password
- Verify the email addresses in `NOTIFICATION_EMAILS` are correctly formatted
- Check your spam folder for notifications 