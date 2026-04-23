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
defined('MOODLE_INTERNAL') || die();

require_once($CFG->libdir.'/formslib.php');
require_once($CFG->dirroot.'/user/lib.php');
require_once('lib.php');

/**
 * Reset forgotten password form definition.
 *
 * @package    core
 * @subpackage auth
 * @copyright  2006 Petr Skoda {@link http://skodak.org}
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
class login_forgot_password_form extends moodleform {

    /**
     * Define the forgot password form.
     */
    function definition() {
        global $USER;

        $mform    = $this->_form;
        $mform->setDisableShortforms(true);

        // Hook for plugins to extend form definition.
        core_login_extend_forgot_password_form($mform);

        $mform->addElement('header', 'searchbyusername', get_string('searchbyusername'), '');

        $purpose = user_edit_map_field_purpose($USER->id, 'username');
        $mform->addElement('text', 'username', get_string('username'), 'size="20"' . $purpose);
        $mform->setType('username', PARAM_RAW);

        $mform->addElement('header', 'searchbyemail', get_string('searchbyemail'), '');

        $purpose = user_edit_map_field_purpose($USER->id, 'email');
        $mform->addElement('text', 'email', get_string('email'), 'maxlength="100" size="30"' . $purpose);
        $mform->setType('email', PARAM_RAW_TRIMMED);

        // Avoid the user to fill both fields.
        $mform->disabledIf('email', 'username', 'neq', '');
        $mform->disabledIf('username', 'email', 'neq', '');

        $mform->addElement('html', '<hr />');

        // Adds a reCAPTCHA element to the forgot password form if the forgot password captcha is enabled.
        if (forgotpassword_captcha_enabled()) {
            $mform->addElement('recaptcha', 'recaptcha_element', '');
        }

        $submitlabel = get_string('search');
        $mform->addElement('submit', 'submit', $submitlabel);
    }

    /**
     * Validate user input from the forgot password form.
     * @param array $data array of submitted form fields.
     * @param array $files submitted with the form.
     * @return array errors occuring during validation.
     */
    function validation($data, $files) {
        global $CFG, $DB, $USER;

        $errors = parent::validation($data, $files);

        if (forgotpassword_captcha_enabled()) {
            $recaptchaelement = $this->_form->getElement('recaptcha_element');
            if (!empty($this->_form->_submitValues['g-recaptcha-response'])) {
                $response = $this->_form->_submitValues['g-recaptcha-response'];
                if (!$recaptchaelement->verify($response)) {
                    $errors['recaptcha_element'] = get_string('incorrectpleasetryagain', 'auth');
                }
            } else {
                $errors['recaptcha_element'] = get_string('missingrecaptchachallengefield');
            }
        }

        // Extend validation for any form extensions from plugins.
        $errors = array_merge($errors, core_login_validate_extend_forgot_password_form($data));

        $errors += core_login_validate_forgot_password_data($data);

        if (!empty($errors)) {
            return $errors;
        }

        // Implement rate limiting to prevent brute force attacks.

        $cache = cache::make('core', 'forgotpassword_rate_limit');

        $ip = 	ool_mfa	ools::get_client_ip() ?: 'unknown';

        // Normalize email and username to lowercase for consistent rate limiting.
        $useridentifier = '';
        if (!empty($data['email'])) {
            $useridentifier = strtolower(trim($data['email']));
        } elseif (!empty($data['username'])) {
            $useridentifier = strtolower(trim($data['username']));
        }

        $now = time();

        // Rate limits configuration.
        $maxip = 5; // Max 5 requests.
        $iperiod = 900; // 15 minutes.
        $maxuser = 3; // Max 3 requests.
        $userperiod = 3600; // 1 hour.

        // Key per IP address.
        $ipkey = 'ip_' . md5($ip);
        // Key per user identifier.
        $userkey = 'user_' . md5($useridentifier);

        $ipdata = $cache->get($ipkey);
        $userdata = $cache->get($userkey);

        // Clean up old attempts and count recent.
        $ipattempts = [];
        if (is_array($ipdata)) {
            foreach ($ipdata as $timestamp) {
                if ($timestamp > $now - $iperiod) {
                    $ipattempts[] = $timestamp;
                }
            }
        }

        $userattempts = [];
        if (is_array($userdata)) {
            foreach ($userdata as $timestamp) {
                if ($timestamp > $now - $userperiod) {
                    $userattempts[] = $timestamp;
                }
            }
        }

        // Check if rate limits exceeded.
        $ipblocked = count($ipattempts) >= $maxip;
        $userblocked = !empty($useridentifier) && (count($userattempts) >= $maxuser);

        if ($ipblocked || $userblocked) {
            // Log the blocked attempt.
            $eventdata = [
                'ip' => $ip,
                'useridentifier' => $useridentifier,
                'time' => $now,
            ];
            debugging('Forgot password rate limit exceeded for IP ' . $ip . ' and user ' . $useridentifier, DEBUG_NORMAL);

            // Throw a generic error.
            $errors['username'] = get_string('forgotpasswordratelimitexceeded', 'auth');
            return $errors;
        }

        // Add current attempt.
        $ipattempts[] = $now;
        $cache->set($ipkey, $ipattempts);

        if (!empty($useridentifier)) {
            $userattempts[] = $now;
            $cache->set($userkey, $userattempts);
        }

        return $errors;
    }

}
