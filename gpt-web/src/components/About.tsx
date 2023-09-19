import React, { useEffect, useState, useRef } from 'react';
import '../css/About.css';

const About: React.FC = () => {

  return (
    <div className="dashboard about-dashboard">
      <h2>About</h2>
      <div className="about-container">
        GPT at home! Basically a better G**gle Nest Hub desk assistant.
        <br/>
        Made with Raspberry Pi and OpenAI API.
        <br/><br/>
        Developed by Judah Paul.
        <br/><br/>
        Learn more @ <a target='_blank' rel='noopener noreferrer'
                      href="https://github.com/judahpaul16/gpt-home">
                      https://github.com/judahpaul16/gpt-home
                    </a>
      </div>
    </div>
  );
};

export default About;
