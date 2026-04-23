<?php
// This file is part of Moodle - http://moodle.org/
//
// Moodle is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// Moodle is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with Moodle.  If not, see <http://www.gnu.org/licenses/>.

/**
 * Forgot password page.
 *
 * @package    core
 * @subpackage auth
 * @copyright  2006 Petr Skoda {@link http://skodak.org}
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

require_once(__DIR__ . '/../../config.php');
require_once($CFG->dirroot . '/login/forgot_password_form.php');
require_once($CFG->dirroot . '/user/lib.php');

$context = context_system::instance();
require_capability('moodle/site:sendmessage', $context);

// Get the user's IP address.
$ip = \core\session\manager::get_ip_address() ?? 'unknown';

try {
    // Define cache for rate limiting.
    $cache = cache::make('core', 'forgotpassword_attempts');
} catch (Exception $e) {
    debugging('Could not initialise cache for forgot password attempts: ' . $e->getMessage(), DEBUG_DEVELOPER);
    // Proceed without rate limiting if cache fails.
    $cache = null;
}

// Rate limit parameters.
$maxattempts = 3;
$period = 300; // 5 minutes in seconds.

$attemptsdata = [];
if ($cache) {
    try {
        $attemptsdata = $cache->get($ip) ?: [];
    } catch (Exception $e) {
        debugging('Could not retrieve forgot password attempts from cache: ' . $e->getMessage(), DEBUG_DEVELOPER);
        // Fallback to empty attempts.
        $attemptsdata = [];
    }
}

// Remove old attempts.
$now = time();
foreach ($attemptsdata as $key => $timestamp) {
    if (($timestamp + $period) < $now) {
        unset($attemptsdata[$key]);
    }
}

// Check if rate limited.
if (count($attemptsdata) >= $maxattempts) {
    $PAGE->set_context($context);
    $PAGE->set_url(new moodle_url('/login/forgot_password.php'));
    $PAGE->set_pagelayout('login');
    echo $OUTPUT->header();
    echo $OUTPUT->notification(get_string('toomanyforgotpasswordattempts', 'core'), 'error');
    echo $OUTPUT->footer();
    exit;
}

$PAGE->set_context($context);
$PAGE->set_url(new moodle_url('/login/forgot_password.php'));
$PAGE->set_pagelayout('login');

$mform = new login_forgot_password_form();

if ($mform->is_cancelled()) {
    redirect(new moodle_url('/'));
} else if ($data = $mform->get_data()) {
    // Validate input properly.
    $email = isset($data->email) ? optional_param('email', '', PARAM_EMAIL) : '';
    $username = isset($data->username) ? optional_param('username', '', PARAM_TEXT) : '';

    // Add current attempt timestamp.
    if ($cache) {
        try {
            $attemptsdata[] = $now;
            $cache->set($ip, $attemptsdata);
        } catch (Exception $e) {
            debugging('Could not update forgot password attempts cache: ' . $e->getMessage(), DEBUG_DEVELOPER);
        }
    }

    // Call the password reset request with validated data.
    user_request_password_reset((object)['email' => $email, 'username' => $username]);

    redirect(new moodle_url('/login/reset_password.php', ['email' => $email, 'username' => $username]));
} else {
    echo $OUTPUT->header();
    $mform->display();
    echo $OUTPUT->footer();
}
