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

use core
otification;

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
        global $DB, $USER, $CFG;
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

        // Implement rate limiting checks
        $ip = $_SERVER['REMOTE_ADDR'] ?? '';

        // Clean and normalize email/username
        $inputuser = trim($data['username'] ?? '');
        $inputemail = trim($data['email'] ?? '');

        $keyemail = '';
        if (!empty($inputuser)) {
            $keyemail = strtolower($inputuser);
        } else if (!empty($inputemail)) {
            $keyemail = strtolower($inputemail);
        }

        $cache = cache::make('core', 'forgotpassword_rate_limit');

        // IP rate limit: max 5 attempts per 15 minutes
        $ipkey = 'ip_' . $ip;
        $ipdata = $cache->get($ipkey);
        if (!$ipdata) {
            $ipdata = ['count' => 0, 'starttime' => time()];
        }
        // Reset count if window expired
        if (time() - $ipdata['starttime'] > 15 * 60) {
            $ipdata = ['count' => 0, 'starttime' => time()];
        }
        if ($ipdata['count'] >= 5) {
            $errors['username'] = get_string('resetpasswordratelimitexceeded', 'auth');
            debugging('Forgot password rate limit reached for IP ' . $ip, DEBUG_NORMAL);
        }

        // User/email rate limit: max 3 attempts per hour
        if ($keyemail !== '') {
            $userkey = 'user_' . md5($keyemail);
            $userdata = $cache->get($userkey);
            if (!$userdata) {
                $userdata = ['count' => 0, 'starttime' => time()];
            }
            // Reset count if window expired
            if (time() - $userdata['starttime'] > 60 * 60) {
                $userdata = ['count' => 0, 'starttime' => time()];
            }
            if ($userdata['count'] >= 3) {
                $errors['username'] = get_string('resetpasswordratelimitexceeded', 'auth');
                debugging('Forgot password rate limit reached for user/email ' . $keyemail, DEBUG_NORMAL);
            }
        }

        // Extend validation for any form extensions from plugins.
        $errors = array_merge($errors, core_login_validate_extend_forgot_password_form($data));

        $errors += core_login_validate_forgot_password_data($data);

        return $errors;
    }

    /**
     * Override submit behaviour to increment rate limits.
     *
     * @param array $data Submitted form data.
     * @return void
     */
    protected function process_data($data) {
        global $CFG;

        $ip = $_SERVER['REMOTE_ADDR'] ?? '';

        $inputuser = trim($data['username'] ?? '');
        $inputemail = trim($data['email'] ?? '');

        $keyemail = '';
        if (!empty($inputuser)) {
            $keyemail = strtolower($inputuser);
        } else if (!empty($inputemail)) {
            $keyemail = strtolower($inputemail);
        }

        $cache = cache::make('core', 'forgotpassword_rate_limit');

        // Update IP data
        $ipkey = 'ip_' . $ip;
        $ipdata = $cache->get($ipkey);
        if (!$ipdata) {
            $ipdata = ['count' => 0, 'starttime' => time()];
        }
        if (time() - $ipdata['starttime'] > 15 * 60) {
            $ipdata = ['count' => 0, 'starttime' => time()];
        }
        $ipdata['count']++;
        $cache->set($ipkey, $ipdata);

        // Update user/email data
        if ($keyemail !== '') {
            $userkey = 'user_' . md5($keyemail);
            $userdata = $cache->get($userkey);
            if (!$userdata) {
                $userdata = ['count' => 0, 'starttime' => time()];
            }
            if (time() - $userdata['starttime'] > 60 * 60) {
                $userdata = ['count' => 0, 'starttime' => time()];
            }
            $userdata['count']++;
            $cache->set($userkey, $userdata);
        }
    }
}
