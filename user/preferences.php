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

use core\output\notification;

defined('MOODLE_INTERNAL') || die();

require_once(__DIR__.'/../../config.php');
require_once($CFG->dirroot.'/user/lib.php');

require_login();
require_sesskey();

$preference = required_param('preference', PARAM_ALPHANUMEXT);
$value = required_param('value', PARAM_TEXT);

// Save preference for current user.
set_user_preference($preference, $value, $USER);

$notification = new notification(get_string('preferencessaved', 'core_user'), notification::NOTIFY_SUCCESS);
echo $OUTPUT->render($notification);
