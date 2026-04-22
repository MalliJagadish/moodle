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

defined('MOODLE_INTERNAL') || die();

require_once(__DIR__.'/../../config.php');
require_once($CFG->dirroot.'/user/lib.php');

require_login();
require_sesskey();

// Example: process preference update
$preference = required_param('preference', PARAM_TEXT);
$value = required_param('value', PARAM_RAW);

// Save preference for current user.
set_user_preference($preference, $value, $USER);

// Redirect or return some response.
echo get_string('preferencessaved', 'core_user');
