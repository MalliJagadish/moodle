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

namespace webservice;

use core_form\form;
use invalid_parameter_exception;

use function validate_ip_or_subnet;

defined('MOODLE_INTERNAL') || die();

/**
 * Token form definition.
 *
 * @package    webservice
 * @copyright  2011 Petr Skoda {@link http://skodak.org}
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
class token_form extends form {

    /**
     * Form definition.
     *
     * @return void
     */
    public function definition() {
        $mform = $this->_form;

        $mform->addElement('text', 'iprestriction', get_string('iprestriction', 'webservice')); // Could be empty.
        $mform->setType('iprestriction', PARAM_RAW_TRIMMED);

        // Other elements here...

        $this->add_action_buttons(true, get_string('savechanges'));
    }

    /**
     * Form validation.
     *
     * @param array $data
     * @param array $files
     * @return array
     */
    public function validation($data, $files) {
        $errors = parent::validation($data, $files);

        if (!empty($data['iprestriction'])) {
            $iplist = preg_split('/[\r\n,]+/', $data['iprestriction'], -1, PREG_SPLIT_NO_EMPTY);
            $invalidips = [];
            foreach ($iplist as $iprestriction) {
                $iprestriction = trim($iprestriction);
                // Use validate_ip_or_subnet to validate each entry.
                if (!validate_ip_or_subnet($iprestriction)) {
                    $invalidips[] = $iprestriction;
                }
            }
            if (!empty($invalidips)) {
                $errors['iprestriction'] = get_string('iprestriction_invalid', 'webservice') . ' (' . implode(', ', $invalidips) . ')';
            }
        }

        return $errors;
    }
}
