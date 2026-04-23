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

// Get the user's IP address.
$ip = \core\session\manager::get_ip_address() ?? 'unknown';

// Define cache for rate limiting.
$cache = cache::make('core', 'forgotpassword_attempts');

// Rate limit parameters.
$maxattempts = 3;
$period = 300; // 5 minutes in seconds.

$attemptsdata = $cache->get($ip);
if (!$attemptsdata) {
    $attemptsdata = [];
}

// Remove old attempts.
$now = time();
foreach ($attemptsdata as $key => $timestamp) {
    if ($timestamp + $period < $now) {
        unset($attemptsdata[$key]);
    }
}

// Check if rate limited.
if (count($attemptsdata) >= $maxattempts) {
    // Display throttle warning.
    $PAGE->set_context(context_system::instance());
    $PAGE->set_url('/login/forgot_password.php');
    $PAGE->set_pagelayout('login');
    echo $OUTPUT->header();
    echo $OUTPUT->notification(get_string('toomanyforgotpasswordattempts', 'core'), 'error');
    echo $OUTPUT->footer();
    exit;
}

// Process the form as before.
$PAGE->set_context(context_system::instance());
$PAGE->set_url(new moodle_url('/login/forgot_password.php'));
$PAGE->set_pagelayout('login');

$mform = new login_forgot_password_form();

if ($mform->is_cancelled()) {
    redirect(new moodle_url('/'));
} else if ($data = $mform->get_data()) {
    // Add current attempt timestamp.
    $attemptsdata[] = $now;
    $cache->set($ip, $attemptsdata);

    // Continue with existing forgot password processing.
    user_request_password_reset($data);

    redirect(new moodle_url('/login/reset_password.php', ['email' => $data->email ?? '', 'username' => $data->username ?? '']));
} else {
    echo $OUTPUT->header();
    $mform->display();
    echo $OUTPUT->footer();
}

// String for the throttle message.
$stringman = get_string_manager();
$stringman->add_string('toomanyforgotpasswordattempts', 'core', 'Too many password reset attempts. Please try again in a few minutes.');
